"""Azure Table Storage persistence for task records."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any, Mapping, TypedDict

from azure.core.exceptions import AzureError, ResourceExistsError, ResourceNotFoundError
from azure.data.tables import TableClient, TableServiceClient, UpdateMode
from dotenv import load_dotenv

TASKS_PARTITION_KEY = "tasks"
DEFAULT_TABLE_NAME = "tasks"
MAX_ID_ALLOCATION_ATTEMPTS = 10

load_dotenv()


class Task(TypedDict):
    """A task as exposed to the CLI and stored by the repository."""

    id: int
    name: str
    description: str
    priority: str
    tags: list[str]
    due_date: str | None
    done: bool
    created_at: str


class _OptionalTaskId(TypedDict, total=False):
    """Optional ID fields accepted while creating a task."""

    id: int


class NewTask(_OptionalTaskId):
    """A task that may not have been assigned a persistent ID."""

    name: str
    description: str
    priority: str
    tags: list[str]
    due_date: str | None
    done: bool
    created_at: str


class StorageConfigurationError(RuntimeError):
    """Raised when Azure Table Storage is not configured correctly."""


class TaskStorageError(RuntimeError):
    """Raised when an Azure Table Storage operation fails."""


class AzureTableTaskRepository:
    """Store task dictionaries in an Azure Table Storage table."""

    def __init__(
        self,
        connection_string: str | None = None,
        table_name: str = DEFAULT_TABLE_NAME,
    ) -> None:
        """Create the table if needed and initialize its client.

        Args:
            connection_string: Azure Storage connection string. When omitted,
                ``AZURE_STORAGE_CONNECTION_STRING`` is read from the environment.
            table_name: Name of the Azure Storage table.

        Raises:
            StorageConfigurationError: If the connection string is missing.
            TaskStorageError: If the Azure table client cannot be initialized.
        """
        resolved_connection_string = (
            connection_string or os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        ).strip()
        if not resolved_connection_string:
            raise StorageConfigurationError(
                "AZURE_STORAGE_CONNECTION_STRING is not set. Add it to the "
                "environment or a .env file before using Azure Table Storage."
            )

        try:
            self._service_client = TableServiceClient.from_connection_string(
                resolved_connection_string
            )
            self._service_client.create_table_if_not_exists(table_name=table_name)
            self._table_client: TableClient = self._service_client.get_table_client(
                table_name=table_name
            )
        except (AzureError, ValueError) as exc:
            raise TaskStorageError(
                f"Could not initialize Azure Table Storage table '{table_name}': {exc}"
            ) from exc

    def list(self) -> list[Task]:
        """Return all tasks ordered by numeric task ID."""
        try:
            entities = self._table_client.query_entities(
                query_filter=f"PartitionKey eq '{TASKS_PARTITION_KEY}'"
            )
            tasks = [_entity_to_task(entity) for entity in entities]
        except (
            AzureError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise TaskStorageError(
                f"Could not list tasks from Azure Table Storage: {exc}"
            ) from exc

        return sorted(tasks, key=lambda task: task["id"])

    def get(self, task_id: int) -> Task | None:
        """Return one task by ID, or ``None`` when it does not exist."""
        _validate_task_id(task_id)
        try:
            entity = self._table_client.get_entity(
                partition_key=TASKS_PARTITION_KEY,
                row_key=str(task_id),
            )
        except ResourceNotFoundError:
            return None
        except AzureError as exc:
            raise TaskStorageError(
                f"Could not get task {task_id} from Azure Table Storage: {exc}"
            ) from exc

        try:
            return _entity_to_task(entity)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TaskStorageError(
                f"Task {task_id} contains invalid data in Azure Table Storage: {exc}"
            ) from exc

    def create(self, task: NewTask) -> Task:
        """Create a task, assigning a collision-safe next ID when none is supplied.

        Supplying an explicit ``id`` preserves that ID. Omitting it allocates the
        current next ID and retries if another writer creates the same row first.
        """
        explicit_id = task.get("id")
        if explicit_id is not None:
            created_task = _task_with_id(task, explicit_id)
            try:
                self._create_entity(created_task)
            except ResourceExistsError as exc:
                raise TaskStorageError(
                    f"Cannot create task {explicit_id}: that ID already exists."
                ) from exc
            return created_task

        for _ in range(MAX_ID_ALLOCATION_ATTEMPTS):
            created_task = _task_with_id(task, self.next_id())
            try:
                self._create_entity(created_task)
            except ResourceExistsError:
                continue
            return created_task

        raise TaskStorageError(
            "Could not allocate a unique task ID after "
            f"{MAX_ID_ALLOCATION_ATTEMPTS} attempts."
        )

    def update(self, task: Task) -> Task:
        """Replace an existing task and return its stored representation."""
        entity = _task_to_entity(task)
        try:
            self._table_client.update_entity(
                entity=entity,
                mode=UpdateMode.REPLACE,
            )
        except ResourceNotFoundError as exc:
            raise TaskStorageError(f"Cannot update missing task {task['id']}.") from exc
        except AzureError as exc:
            raise TaskStorageError(
                f"Could not update task {task['id']} in Azure Table Storage: {exc}"
            ) from exc
        return _entity_to_task(entity)

    def delete(self, task_id: int) -> bool:
        """Delete a task, returning whether a task was removed."""
        _validate_task_id(task_id)
        try:
            self._table_client.delete_entity(
                partition_key=TASKS_PARTITION_KEY,
                row_key=str(task_id),
            )
        except ResourceNotFoundError:
            return False
        except AzureError as exc:
            raise TaskStorageError(
                f"Could not delete task {task_id} from Azure Table Storage: {exc}"
            ) from exc
        return True

    def next_id(self) -> int:
        """Return one greater than the largest numeric task ID."""
        try:
            entities = self._table_client.query_entities(
                query_filter=f"PartitionKey eq '{TASKS_PARTITION_KEY}'",
                select=["RowKey"],
            )
            task_ids = [
                int(str(entity["RowKey"]))
                for entity in entities
                if str(entity.get("RowKey", "")).isdigit()
            ]
        except (AzureError, KeyError, TypeError, ValueError) as exc:
            raise TaskStorageError(
                f"Could not determine the next task ID from Azure Table Storage: {exc}"
            ) from exc
        return max(task_ids, default=0) + 1

    def _create_entity(self, task: Task) -> None:
        """Create one Azure entity while preserving conflict errors for retries."""
        try:
            self._table_client.create_entity(entity=_task_to_entity(task))
        except ResourceExistsError:
            raise
        except AzureError as exc:
            raise TaskStorageError(
                f"Could not create task {task['id']} in Azure Table Storage: {exc}"
            ) from exc


def _task_to_entity(task: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a task mapping to an Azure Table entity."""
    task_id = task["id"]
    _validate_task_id(task_id)

    tags = task["tags"]
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("task tags must be a list of strings")

    return {
        "PartitionKey": TASKS_PARTITION_KEY,
        "RowKey": str(task_id),
        "name": _required_string(task, "name"),
        "description": _required_string(task, "description"),
        "priority": _required_string(task, "priority"),
        "tags": json.dumps(tags, ensure_ascii=False),
        "due_date": _optional_iso_string(task.get("due_date")),
        "done": _required_bool(task, "done"),
        "created_at": _required_iso_string(task, "created_at"),
    }


def _entity_to_task(entity: Mapping[str, Any]) -> Task:
    """Convert an Azure Table entity to the CLI task schema."""
    tags = json.loads(_required_string(entity, "tags"))
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("stored task tags must decode to a list of strings")

    due_date = _required_string(entity, "due_date")
    return {
        "id": int(_required_string(entity, "RowKey")),
        "name": _required_string(entity, "name"),
        "description": _required_string(entity, "description"),
        "priority": _required_string(entity, "priority"),
        "tags": tags,
        "due_date": due_date or None,
        "done": _required_bool(entity, "done"),
        "created_at": _required_string(entity, "created_at"),
    }


def _task_with_id(task: Mapping[str, Any], task_id: int) -> Task:
    """Return a fully typed task with the supplied ID."""
    return _entity_to_task(_task_to_entity({**task, "id": task_id}))


def _validate_task_id(task_id: object) -> None:
    """Validate that a task ID is a positive, non-boolean integer."""
    if isinstance(task_id, bool) or not isinstance(task_id, int) or task_id < 1:
        raise ValueError("task id must be a positive integer")


def _required_string(values: Mapping[str, Any], key: str) -> str:
    """Read a required string value from a mapping."""
    value = values[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _required_bool(values: Mapping[str, Any], key: str) -> bool:
    """Read a required Boolean value from a mapping."""
    value = values[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


def _required_iso_string(values: Mapping[str, Any], key: str) -> str:
    """Read a required date, datetime, or ISO string as text."""
    value = values[key]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    raise TypeError(f"{key} must be an ISO string, date, or datetime")


def _optional_iso_string(value: object) -> str:
    """Convert an optional date-like value to an Azure-supported string."""
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    raise TypeError("due_date must be an ISO string, date, datetime, or None")

"""Shared pytest fixtures for the task manager test suite."""

from pathlib import Path
from typing import Any

import pytest
from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError

import app
import storage


class FakeTableClient:
    """In-memory Azure Table client used to keep tests network-free."""

    def __init__(self) -> None:
        self.entities: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: list[tuple[str, Any]] = []
        self.query_error: Exception | None = None
        self.write_error: Exception | None = None

    def query_entities(
        self,
        query_filter: str | None = None,
        select: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return copied entities, optionally filtered to the tasks partition."""
        self.calls.append(
            ("query_entities", {"query_filter": query_filter, "select": select})
        )
        if self.query_error is not None:
            raise self.query_error
        entities = self.entities.values()
        if query_filter and "PartitionKey eq 'tasks'" in query_filter:
            entities = (
                entity
                for entity in entities
                if entity.get("PartitionKey") == "tasks"
            )
        copied_entities = [dict(entity) for entity in entities]
        if select is not None:
            return [
                {key: entity[key] for key in select if key in entity}
                for entity in copied_entities
            ]
        return copied_entities

    def list_entities(self) -> list[dict[str, Any]]:
        """Return all copied entities."""
        self.calls.append(("list_entities", None))
        if self.query_error is not None:
            raise self.query_error
        return [dict(entity) for entity in self.entities.values()]

    def upsert_entity(
        self, entity: dict[str, Any], mode: Any = None
    ) -> None:
        """Insert or replace an entity."""
        self.calls.append(("upsert_entity", dict(entity)))
        if self.write_error is not None:
            raise self.write_error
        key = (str(entity["PartitionKey"]), str(entity["RowKey"]))
        self.entities[key] = dict(entity)

    def create_entity(self, entity: dict[str, Any]) -> None:
        """Insert an entity."""
        self.calls.append(("create_entity", dict(entity)))
        if self.write_error is not None:
            raise self.write_error
        key = (str(entity["PartitionKey"]), str(entity["RowKey"]))
        if key in self.entities:
            raise ResourceExistsError("entity already exists")
        self.entities[key] = dict(entity)

    def update_entity(
        self, entity: dict[str, Any], mode: Any = None
    ) -> None:
        """Replace an existing entity."""
        self.calls.append(("update_entity", dict(entity)))
        if self.write_error is not None:
            raise self.write_error
        key = (str(entity["PartitionKey"]), str(entity["RowKey"]))
        if key not in self.entities:
            raise ResourceNotFoundError("entity does not exist")
        self.entities[key] = dict(entity)

    def get_entity(self, partition_key: str, row_key: str) -> dict[str, Any]:
        """Return an entity by key or emulate Azure's not-found response."""
        self.calls.append(("get_entity", (partition_key, row_key)))
        if self.query_error is not None:
            raise self.query_error
        try:
            return dict(self.entities[(str(partition_key), str(row_key))])
        except KeyError as exc:
            raise ResourceNotFoundError("entity does not exist") from exc

    def delete_entity(
        self,
        partition_key: str | None = None,
        row_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Delete an entity by its Azure Table keys."""
        partition_key = partition_key or kwargs.get("PartitionKey")
        row_key = row_key or kwargs.get("RowKey")
        self.calls.append(("delete_entity", (partition_key, row_key)))
        if self.write_error is not None:
            raise self.write_error
        key = (str(partition_key), str(row_key))
        if key not in self.entities:
            raise ResourceNotFoundError("entity does not exist")
        del self.entities[key]


class FakeTableServiceClient:
    """Minimal TableServiceClient replacement sharing one fake table."""

    def __init__(self, table_client: FakeTableClient) -> None:
        self.table_client = table_client
        self.connection_strings: list[str] = []
        self.table_names: list[str] = []

    def from_connection_string(self, connection_string: str) -> "FakeTableServiceClient":
        """Record configuration and return this fake service."""
        self.connection_strings.append(connection_string)
        return self

    def get_table_client(self, table_name: str) -> FakeTableClient:
        """Return the in-memory table client."""
        self.table_names.append(table_name)
        return self.table_client

    def create_table_if_not_exists(self, table_name: str) -> FakeTableClient:
        """Return the in-memory table client for create-if-missing flows."""
        self.table_names.append(table_name)
        return self.table_client


class FakeDirectTableClient:
    """TableClient.from_connection_string adapter for alternate implementations."""

    def __init__(self, table_client: FakeTableClient) -> None:
        self.table_client = table_client
        self.connection_strings: list[str] = []
        self.table_names: list[str] = []

    def from_connection_string(
        self, connection_string: str, table_name: str
    ) -> FakeTableClient:
        """Record configuration and return the shared in-memory table."""
        self.connection_strings.append(connection_string)
        self.table_names.append(table_name)
        return self.table_client


@pytest.fixture()
def mock_table_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeTableClient:
    """Inject fake Azure Table clients and a non-secret connection string."""
    table_client = FakeTableClient()
    service_client = FakeTableServiceClient(table_client)
    direct_client = FakeDirectTableClient(table_client)
    monkeypatch.setenv(
        "AZURE_STORAGE_CONNECTION_STRING",
        "DefaultEndpointsProtocol=https;AccountName=test;AccountKey=fake",
    )
    monkeypatch.setattr(
        storage, "TableServiceClient", service_client, raising=True
    )
    monkeypatch.setattr(storage, "TableClient", direct_client, raising=True)
    monkeypatch.setattr(app, "TableServiceClient", service_client, raising=False)
    monkeypatch.setattr(app, "TableClient", direct_client, raising=False)
    monkeypatch.setattr(app, "_task_repository", None)
    return table_client


@pytest.fixture(autouse=True)
def isolated_tasks_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_table_storage: FakeTableClient,
) -> Path:
    """Isolate legacy JSON code while the Azure storage migration lands.

    Returns:
        A temporary path retained for compatibility with pre-migration tests.
    """
    tasks_file = tmp_path / "tasks.json"
    monkeypatch.setattr(app, "TASKS_FILE", tasks_file)
    return tasks_file


@pytest.fixture()
def sample_tasks(isolated_tasks_file: Path) -> list[dict]:
    """Seed the configured task repository with sample tasks.

    Returns:
        The list of task dictionaries written to storage.
    """
    tasks = [
        {
            "id": 1,
            "name": "Buy groceries",
            "description": "",
            "priority": "low",
            "tags": ["personal"],
            "due_date": None,
            "done": False,
            "created_at": "2025-01-01T09:00:00",
        },
        {
            "id": 2,
            "name": "Deploy to production",
            "description": "Run the release pipeline",
            "priority": "high",
            "tags": ["work", "devops"],
            "due_date": "2020-01-01",  # deliberately overdue
            "done": False,
            "created_at": "2025-01-02T10:00:00",
        },
        {
            "id": 3,
            "name": "Write unit tests",
            "description": "",
            "priority": "medium",
            "tags": ["work"],
            "due_date": None,
            "done": True,
            "created_at": "2025-01-03T11:00:00",
        },
    ]
    app.save_tasks(tasks)
    return tasks

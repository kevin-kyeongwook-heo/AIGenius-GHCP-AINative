"""Mocked tests for Azure Table Storage task persistence."""

import json
from unittest.mock import MagicMock

import pytest
from azure.core.exceptions import AzureError
from click.testing import CliRunner

import app
from storage import TaskStorageError
from tests.conftest import FakeTableClient


FULL_TASK = {
    "id": 7,
    "name": "Deploy to production",
    "description": "Run the release pipeline",
    "priority": "high",
    "tags": ["work", "devops"],
    "due_date": "2026-12-31",
    "done": False,
    "created_at": "2026-10-01T09:00:00",
}


def _stored_task_entity(table_client: FakeTableClient) -> dict:
    task_entities = [
        entity
        for entity in table_client.entities.values()
        if entity.get("PartitionKey") == "tasks"
    ]
    assert len(task_entities) == 1
    return task_entities[0]


class TestAzureTableRepository:
    def test_task_round_trips_through_entity_conversion(
        self, mock_table_storage: FakeTableClient
    ) -> None:
        app.save_tasks([FULL_TASK])

        assert app.load_tasks() == [FULL_TASK]

    def test_stores_required_partition_and_row_keys(
        self, mock_table_storage: FakeTableClient
    ) -> None:
        app.save_tasks([FULL_TASK])

        entity = _stored_task_entity(mock_table_storage)
        assert entity["PartitionKey"] == "tasks"
        assert entity["RowKey"] == "7"

    def test_serializes_tags_to_table_supported_value(
        self, mock_table_storage: FakeTableClient
    ) -> None:
        app.save_tasks([FULL_TASK])

        entity = _stored_task_entity(mock_table_storage)
        assert isinstance(entity["tags"], str)
        assert json.loads(entity["tags"]) == ["work", "devops"]

    def test_create_update_and_delete_are_persisted(
        self, mock_table_storage: FakeTableClient
    ) -> None:
        app.save_tasks([FULL_TASK])
        updated_task = {**FULL_TASK, "name": "Deploy safely", "done": True}
        app.save_tasks([updated_task])

        assert app.load_tasks() == [updated_task]

        app.save_tasks([])

        assert app.load_tasks() == []
        operation_names = [name for name, _ in mock_table_storage.calls]
        assert any(name in operation_names for name in ("upsert_entity", "create_entity"))
        assert "delete_entity" in operation_names

    def test_empty_storage_returns_empty_list(
        self, mock_table_storage: FakeTableClient
    ) -> None:
        assert app.load_tasks() == []

    def test_load_orders_numeric_ids_and_next_id_uses_maximum(
        self, mock_table_storage: FakeTableClient
    ) -> None:
        tasks = [
            {**FULL_TASK, "id": 10, "name": "Tenth"},
            {**FULL_TASK, "id": 2, "name": "Second"},
        ]
        app.save_tasks(tasks)

        loaded_tasks = app.load_tasks()

        assert [task["id"] for task in loaded_tasks] == [2, 10]
        assert app.next_id(loaded_tasks) == 11

    @pytest.mark.parametrize("invalid_id", [0, -1, True])
    def test_repository_rejects_invalid_ids(
        self, invalid_id: int, mock_table_storage: FakeTableClient
    ) -> None:
        repository = app.get_task_repository()

        with pytest.raises(ValueError, match="positive integer"):
            repository.get(invalid_id)
        with pytest.raises(ValueError, match="positive integer"):
            repository.delete(invalid_id)

    def test_missing_connection_string_is_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING")

        with pytest.raises(Exception, match="AZURE_STORAGE_CONNECTION_STRING"):
            app.load_tasks()

    def test_query_failure_is_not_treated_as_empty_storage(
        self, mock_table_storage: FakeTableClient
    ) -> None:
        mock_table_storage.query_error = AzureError("Azure query failed")

        with pytest.raises(TaskStorageError, match="Azure query failed"):
            app.load_tasks()

    def test_write_failure_is_propagated(
        self, mock_table_storage: FakeTableClient
    ) -> None:
        mock_table_storage.write_error = AzureError("Azure write failed")

        with pytest.raises(TaskStorageError, match="Azure write failed"):
            app.save_tasks([FULL_TASK])


class TestAzureBackedCli:
    @pytest.fixture(autouse=True)
    def disable_ai_suggestion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(app, "suggest_tag", MagicMock(return_value=None))

    @pytest.fixture()
    def runner(self) -> CliRunner:
        return CliRunner()

    def test_add_and_list_use_table_storage(
        self, runner: CliRunner, mock_table_storage: FakeTableClient
    ) -> None:
        add_result = runner.invoke(
            app.cli,
            ["add", "Ship release", "--priority", "high", "--tag", "work"],
        )
        list_result = runner.invoke(app.cli, ["list"])

        assert add_result.exit_code == 0
        assert list_result.exit_code == 0
        assert "Ship release" in list_result.output
        assert _stored_task_entity(mock_table_storage)["RowKey"] == "1"

    def test_add_uses_next_id_after_gaps(
        self, runner: CliRunner, mock_table_storage: FakeTableClient
    ) -> None:
        app.save_tasks(
            [
                {**FULL_TASK, "id": 2, "name": "Second"},
                {**FULL_TASK, "id": 9, "name": "Ninth"},
            ]
        )

        result = runner.invoke(app.cli, ["add", "Tenth", "--no-ai"])

        assert result.exit_code == 0
        assert sorted(task["id"] for task in app.load_tasks()) == [2, 9, 10]

    @pytest.mark.parametrize("command", ["complete", "edit", "delete"])
    def test_mutating_commands_reject_invalid_ids(
        self, runner: CliRunner, command: str
    ) -> None:
        arguments = [command, "999"]
        if command == "edit":
            arguments.extend(["--name", "Missing"])

        result = runner.invoke(app.cli, arguments)

        assert result.exit_code != 0
        assert "No task found with ID 999" in result.output

    def test_complete_edit_delete_and_stats_persist(
        self, runner: CliRunner, mock_table_storage: FakeTableClient
    ) -> None:
        app.save_tasks(
            [
                {**FULL_TASK, "id": 1, "name": "First"},
                {**FULL_TASK, "id": 2, "name": "Second", "priority": "low"},
            ]
        )

        complete_result = runner.invoke(app.cli, ["complete", "1"])
        edit_result = runner.invoke(
            app.cli, ["edit", "2", "--name", "Updated", "--priority", "medium"]
        )
        stats_result = runner.invoke(app.cli, ["stats"])
        delete_result = runner.invoke(app.cli, ["delete", "1"])

        assert complete_result.exit_code == 0
        assert edit_result.exit_code == 0
        assert stats_result.exit_code == 0
        assert "2" in stats_result.output
        assert delete_result.exit_code == 0
        assert app.load_tasks() == [
            {
                **FULL_TASK,
                "id": 2,
                "name": "Updated",
                "priority": "medium",
            }
        ]
        assert ("tasks", "1") not in mock_table_storage.entities

    def test_sdk_failure_makes_cli_command_fail(
        self,
        runner: CliRunner,
        mock_table_storage: FakeTableClient,
    ) -> None:
        mock_table_storage.query_error = AzureError("Azure unavailable")

        result = runner.invoke(app.cli, ["list"])

        assert result.exit_code != 0
        assert isinstance(result.exception, TaskStorageError)

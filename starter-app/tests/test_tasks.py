"""Unit tests for the Task Manager CLI."""

import json
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from app import (
    add,
    cli,
    complete,
    delete,
    edit,
    highlight_matches,
    is_overdue,
    list_tasks,
    load_tasks,
    save_tasks,
    stats,
)


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


class TestLoadTasks:
    def test_returns_empty_list_when_file_missing(self, isolated_tasks_file: Path) -> None:
        assert load_tasks() == []

    def test_loads_existing_tasks(self, isolated_tasks_file: Path) -> None:
        tasks = [{"id": 1, "name": "Test", "done": False}]
        isolated_tasks_file.write_text(json.dumps(tasks), encoding="utf-8")
        assert load_tasks() == tasks

    def test_returns_empty_list_on_corrupt_file(self, isolated_tasks_file: Path) -> None:
        isolated_tasks_file.write_text("not-json", encoding="utf-8")
        assert load_tasks() == []

    def test_returns_empty_list_when_file_contains_object(self, isolated_tasks_file: Path) -> None:
        isolated_tasks_file.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        assert load_tasks() == []


class TestSaveTasks:
    def test_saves_and_reloads(self, isolated_tasks_file: Path) -> None:
        tasks = [{"id": 1, "name": "Test", "done": False}]
        save_tasks(tasks)
        assert load_tasks() == tasks

    def test_saves_empty_list(self, isolated_tasks_file: Path) -> None:
        save_tasks([])
        assert load_tasks() == []


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


class TestIsOverdue:
    def test_past_due_date_is_overdue(self) -> None:
        task = {"done": False, "due_date": "2000-01-01"}
        assert is_overdue(task) is True

    def test_future_due_date_is_not_overdue(self) -> None:
        task = {"done": False, "due_date": "2099-12-31"}
        assert is_overdue(task) is False

    def test_done_task_is_never_overdue(self) -> None:
        task = {"done": True, "due_date": "2000-01-01"}
        assert is_overdue(task) is False

    def test_no_due_date_is_not_overdue(self) -> None:
        task = {"done": False, "due_date": None}
        assert is_overdue(task) is False

    def test_invalid_due_date_is_not_overdue(self) -> None:
        task = {"done": False, "due_date": "not-a-date"}
        assert is_overdue(task) is False


# ---------------------------------------------------------------------------
# CLI commands via CliRunner
# ---------------------------------------------------------------------------


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class TestAddCommand:
    def test_add_creates_task(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["add", "Buy milk"])
        assert result.exit_code == 0
        tasks = load_tasks()
        assert len(tasks) == 1
        assert tasks[0]["name"] == "Buy milk"
        assert tasks[0]["done"] is False

    def test_add_sets_defaults(self, runner: CliRunner) -> None:
        runner.invoke(cli, ["add", "Task"])
        task = load_tasks()[0]
        assert task["priority"] == "medium"
        assert task["tags"] == []
        assert task["due_date"] is None
        assert task["description"] == ""
        assert "created_at" in task

    def test_add_with_options(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli,
            ["add", "Deploy", "--priority", "high", "--due", "2099-12-31", "--tag", "work", "--tag", "devops"],
        )
        assert result.exit_code == 0
        task = load_tasks()[0]
        assert task["priority"] == "high"
        assert task["due_date"] == "2099-12-31"
        assert task["tags"] == ["work", "devops"]

    def test_add_empty_name_fails(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["add", "   "])
        assert result.exit_code != 0
        assert load_tasks() == []

    def test_add_name_too_long_fails(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["add", "x" * 201])
        assert result.exit_code != 0

    def test_add_invalid_due_date_fails(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["add", "Task", "--due", "31-12-2099"])
        assert result.exit_code != 0
        assert load_tasks() == []

    def test_add_assigns_sequential_ids(self, runner: CliRunner) -> None:
        runner.invoke(cli, ["add", "First"])
        runner.invoke(cli, ["add", "Second"])
        ids = [t["id"] for t in load_tasks()]
        assert ids == [1, 2]

    def test_add_duplicate_name_fails_without_adding_task(self, runner: CliRunner) -> None:
        first_result = runner.invoke(cli, ["add", "Task"])
        duplicate_result = runner.invoke(cli, ["add", "Task"])

        assert first_result.exit_code == 0
        assert duplicate_result.exit_code == 1
        assert "already exists" in duplicate_result.output
        assert len(load_tasks()) == 1


class TestListCommand:
    def test_list_empty(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No tasks" in result.output

    def test_list_shows_tasks(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "Buy groceries" in result.output
        assert "Deploy to production" in result.output

    def test_list_filter_pending(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["list", "--status", "pending"])
        assert result.exit_code == 0
        assert "Write unit tests" not in result.output  # it's done

    def test_list_filter_done(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["list", "--status", "done"])
        assert result.exit_code == 0
        assert "Write unit tests" in result.output
        assert "Buy groceries" not in result.output

    def test_list_filter_priority(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["list", "--priority", "high"])
        assert result.exit_code == 0
        assert "Deploy to production" in result.output
        assert "Buy groceries" not in result.output

    def test_list_filter_tag(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["list", "--tag", "personal"])
        assert result.exit_code == 0
        assert "Buy groceries" in result.output
        assert "Deploy to production" not in result.output

    def test_list_filter_overdue(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["list", "--overdue"])
        assert result.exit_code == 0
        assert "Deploy to production" in result.output  # due 2020-01-01
        assert "Buy groceries" not in result.output

    def test_list_no_match_message(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["list", "--tag", "nonexistent"])
        assert result.exit_code == 0
        assert "No tasks match" in result.output


class TestSearchCommand:
    def test_search_matches_name_and_description(
        self, runner: CliRunner, sample_tasks: list[dict]
    ) -> None:
        name_result = runner.invoke(cli, ["search", "DEPLOY"])
        description_result = runner.invoke(cli, ["search", "release"])

        assert name_result.exit_code == 0
        assert "Deploy to production" in name_result.output
        assert "Buy groceries" not in name_result.output
        assert description_result.exit_code == 0
        assert "Run the release pipeline" in description_result.output
        assert "Buy groceries" not in description_result.output

    def test_search_sorts_by_descending_priority(
        self, runner: CliRunner, isolated_tasks_file: Path
    ) -> None:
        tasks = [
            {"id": 1, "name": "Low keyword", "description": "", "priority": "low", "done": False},
            {"id": 2, "name": "High keyword", "description": "", "priority": "high", "done": False},
            {"id": 3, "name": "Medium keyword", "description": "", "priority": "medium", "done": False},
        ]
        save_tasks(tasks)

        result = runner.invoke(cli, ["search", "keyword"])

        assert result.exit_code == 0
        assert result.output.index("High keyword") < result.output.index("Medium keyword")
        assert result.output.index("Medium keyword") < result.output.index("Low keyword")

    def test_search_highlights_matches(self) -> None:
        highlighted = highlight_matches("Deploy release", "release")

        assert highlighted.plain == "Deploy release"
        assert any(span.style == "bold yellow" for span in highlighted.spans)

    def test_search_no_matches(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["search", "unknown"])

        assert result.exit_code == 0
        assert "No tasks match 'unknown'" in result.output

    def test_search_rejects_empty_keyword(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["search", "   "])

        assert result.exit_code != 0
        assert "keyword cannot be empty" in result.output

    def test_search_requires_keyword(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["search"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output


class TestCompleteCommand:
    def test_complete_marks_done(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["complete", "1"])
        assert result.exit_code == 0
        task = next(t for t in load_tasks() if t["id"] == 1)
        assert task["done"] is True

    def test_complete_already_done(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["complete", "3"])  # task 3 is already done
        assert result.exit_code == 0
        assert "already" in result.output

    def test_complete_nonexistent_id_fails(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["complete", "999"])
        assert result.exit_code != 0


class TestEditCommand:
    def test_edit_name(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["edit", "1", "--name", "New name"])
        assert result.exit_code == 0
        task = next(t for t in load_tasks() if t["id"] == 1)
        assert task["name"] == "New name"

    def test_edit_priority(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["edit", "1", "--priority", "high"])
        assert result.exit_code == 0
        task = next(t for t in load_tasks() if t["id"] == 1)
        assert task["priority"] == "high"

    def test_edit_due_date(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["edit", "1", "--due", "2099-06-30"])
        assert result.exit_code == 0
        task = next(t for t in load_tasks() if t["id"] == 1)
        assert task["due_date"] == "2099-06-30"

    def test_edit_clear_due_date(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["edit", "2", "--due", ""])
        assert result.exit_code == 0
        task = next(t for t in load_tasks() if t["id"] == 2)
        assert task["due_date"] is None

    def test_edit_tags(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["edit", "1", "--tag", "home", "--tag", "urgent"])
        assert result.exit_code == 0
        task = next(t for t in load_tasks() if t["id"] == 1)
        assert task["tags"] == ["home", "urgent"]

    def test_edit_no_changes_warns(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["edit", "1"])
        assert result.exit_code == 0
        assert "No changes" in result.output

    def test_edit_nonexistent_id_fails(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["edit", "999", "--name", "Nope"])
        assert result.exit_code != 0

    def test_edit_invalid_due_date_fails(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["edit", "1", "--due", "bad-date"])
        assert result.exit_code != 0


class TestDeleteCommand:
    def test_delete_removes_task(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["delete", "1"])
        assert result.exit_code == 0
        ids = [t["id"] for t in load_tasks()]
        assert 1 not in ids

    def test_delete_nonexistent_id_fails(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["delete", "999"])
        assert result.exit_code != 0


class TestStatsCommand:
    def test_stats_empty(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["stats"])
        assert result.exit_code == 0
        assert "0" in result.output

    def test_stats_counts(self, runner: CliRunner, sample_tasks: list[dict]) -> None:
        result = runner.invoke(cli, ["stats"])
        assert result.exit_code == 0
        assert "3" in result.output  # total

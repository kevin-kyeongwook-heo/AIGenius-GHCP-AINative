"""
작업 관리자 CLI -- AI Genius 에피소드 1 워크숍 스타터 앱

GitHub Copilot을 활용한 AI 네이티브 워크플로우 확장을 보여주는
실제 Python 프로젝트 기반의 명령줄 작업 관리자입니다.

사용법:
    python app.py add "Buy groceries"
    python app.py add "Deploy to production" --priority high --due 2025-12-31 --tag work
    python app.py list
    python app.py list --status pending --priority high
    python app.py list --overdue
    python app.py search "keyword"
    python app.py complete 1
    python app.py edit 1 --priority low --due 2026-01-15
    python app.py delete 1
    python app.py stats
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import cast

import click
from rich.console import Console
from rich.table import Table
from rich.text import Text

from ai import TagSuggestionError, suggest_tag
from storage import (
    AzureTableTaskRepository,
    NewTask,
    StorageConfigurationError,
    Task,
    TaskStorageError,
)

# Retained for compatibility with extensions that import the old constant.
TASKS_FILE = Path(__file__).resolve().with_name("tasks.json")

PRIORITIES = ("low", "medium", "high")
PRIORITY_COLOURS = {"low": "cyan", "medium": "yellow", "high": "red"}

console = Console()
_task_repository: AzureTableTaskRepository | None = None


# ---------------------------------------------------------------------------
# 저장소 도우미
# ---------------------------------------------------------------------------


def get_task_repository() -> AzureTableTaskRepository:
    """Return the process-wide Azure Table task repository."""
    global _task_repository
    if _task_repository is None:
        _task_repository = AzureTableTaskRepository()
    return _task_repository


def load_tasks() -> list[dict]:
    """Load all tasks from Azure Table Storage."""
    return [dict(task) for task in get_task_repository().list()]


def save_tasks(tasks: list[dict]) -> None:
    """Synchronize a complete task list to Azure Table Storage.

    This compatibility helper preserves the previous public API. CLI mutations
    use repository CRUD methods directly to avoid rewriting unrelated tasks.
    """
    repository = get_task_repository()
    existing_ids = {task["id"] for task in repository.list()}
    desired_ids = {task["id"] for task in tasks}

    for task in tasks:
        if task["id"] in existing_ids:
            repository.update(cast(Task, task))
        else:
            repository.create(cast(NewTask, task))

    for task_id in existing_ids - desired_ids:
        repository.delete(task_id)


def next_id(tasks: list[dict]) -> int:
    """사용 가능한 다음 작업 ID를 계산합니다.

    인수:
        tasks: 현재 작업 목록입니다.

    반환값:
        현재 최댓값보다 1 큰 정수 ID를 반환합니다. 작업이 없으면 1을 반환합니다.
    """
    if not tasks:
        return 1
    return max(t["id"] for t in tasks) + 1


# ---------------------------------------------------------------------------
# 도메인 도우미
# ---------------------------------------------------------------------------


def is_overdue(task: dict) -> bool:
    """대기 중인 작업의 마감일이 지났으면 True를 반환합니다.

    인수:
        task: 작업 딕셔너리입니다.

    반환값:
        작업이 완료되지 않았고 due_date가 오늘보다 이전이면 True를 반환합니다.
    """
    if task.get("done"):
        return False
    due = task.get("due_date")
    if not due:
        return False
    try:
        return date.fromisoformat(due) < date.today()
    except ValueError:
        return False


def format_due(task: dict) -> Text:
    """긴급도에 따라 색상을 적용하여 마감일을 표시합니다.

    인수:
        task: 작업 딕셔너리입니다.

    반환값:
        Rich Text 객체입니다. 기한이 지났으면 빨간색, 오늘이면 노란색,
        그 외에는 기본 색상으로 표시합니다.
    """
    due = task.get("due_date", "")
    if not due:
        return Text("—", style="dim")
    try:
        due_date = date.fromisoformat(due)
    except ValueError:
        return Text(due, style="dim")

    today = date.today()
    if due_date < today:
        return Text(due, style="bold red")
    if due_date == today:
        return Text(due, style="yellow")
    return Text(due)


def find_task(tasks: list[dict], task_id: int) -> dict | None:
    """정수 ID로 작업을 찾습니다.

    인수:
        tasks: 검색할 작업 목록입니다.
        task_id: 찾을 ID입니다.

    반환값:
        일치하는 작업 딕셔너리이며, 찾지 못하면 None입니다.
    """
    return next((t for t in tasks if t["id"] == task_id), None)


def highlight_matches(value: str, keyword: str) -> Text:
    """검색어와 일치하는 텍스트를 강조 표시합니다.

    인수:
        value: 검색어를 포함할 수 있는 텍스트입니다.
        keyword: 강조 표시할 검색어입니다.

    반환값:
        일치하는 부분이 굵은 노란색으로 표시된 Rich Text 객체입니다.
    """
    text = Text(value)
    for match in re.finditer(re.escape(keyword), value, re.IGNORECASE):
        text.stylize("bold yellow", match.start(), match.end())
    return text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """터미널에서 할 일 목록을 관리하는 작업 관리자입니다."""
    try:
        get_task_repository()
    except (StorageConfigurationError, TaskStorageError) as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.argument("name")
@click.option(
    "--priority",
    "-p",
    type=click.Choice(PRIORITIES),
    default="medium",
    show_default=True,
    help="작업 우선순위.",
)
@click.option("--description", "-d", default="", help="선택 사항인 자세한 설명.")
@click.option(
    "--due",
    default=None,
    metavar="YYYY-MM-DD",
    help="선택 사항인 마감일 (ISO 8601).",
)
@click.option(
    "--tag",
    "-t",
    multiple=True,
    metavar="TAG",
    help="추가할 태그 (여러 번 지정할 수 있음).",
)
@click.option(
    "--no-ai",
    is_flag=True,
    default=False,
    help="Azure OpenAI 자동 태그 추천을 건너뜁니다.",
)
def add(
    name: str,
    priority: str,
    description: str,
    due: str | None,
    tag: tuple[str, ...],
    no_ai: bool,
) -> None:
    """새 작업을 추가합니다.

    NAME은 추가할 작업의 제목입니다.
    """
    name = name.strip()
    if not name:
        console.print("[red]Error: Task name cannot be empty.[/red]")
        sys.exit(1)
    if len(name) > 200:
        console.print("[red]Error: Task name cannot exceed 200 characters.[/red]")
        sys.exit(1)

    if due:
        try:
            date.fromisoformat(due)
        except ValueError:
            console.print(f"[red]Error: '{due}' is not a valid date. Use YYYY-MM-DD format.[/red]")
            sys.exit(1)

    tasks = load_tasks()
    if any(task.get("name") == name for task in tasks):
        console.print(f"[red]Error: A task named '{name}' already exists.[/red]")
        sys.exit(1)

    tags = list(tag)
    suggested_tag: str | None = None
    if not tags and not no_ai:
        try:
            suggested_tag = suggest_tag(name, description)
        except TagSuggestionError:
            console.print(
                "[yellow]Warning: AI tag suggestion failed; saving the task without a tag.[/yellow]"
            )
        if suggested_tag:
            tags.append(suggested_tag)

    new_task: NewTask = {
        "name": name,
        "description": description.strip(),
        "priority": priority,
        "tags": tags,
        "due_date": due,
        "done": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    task = get_task_repository().create(new_task)

    priority_colour = PRIORITY_COLOURS[priority]
    console.print(
        f"[green]Added task #[bold]{task['id']}[/bold][/green]: {name} "
        f"[[{priority_colour}]{priority}[/{priority_colour}]]"
    )
    if suggested_tag:
        console.print(f"[cyan]AI suggested tag: {suggested_tag}[/cyan]")


@cli.command(name="list")
@click.option(
    "--status",
    type=click.Choice(["pending", "done", "all"]),
    default="all",
    show_default=True,
    help="완료 상태로 필터링합니다.",
)
@click.option(
    "--priority",
    "-p",
    type=click.Choice(PRIORITIES),
    default=None,
    help="우선순위로 필터링합니다.",
)
@click.option("--tag", "-t", default=None, metavar="TAG", help="태그로 필터링합니다.")
@click.option("--overdue", is_flag=True, default=False, help="기한이 지난 작업만 표시합니다.")
def list_tasks(status: str, priority: str | None, tag: str | None, overdue: bool) -> None:
    """선택 사항인 필터를 적용하여 작업을 나열합니다."""
    tasks = load_tasks()

    if not tasks:
        console.print("[yellow]No tasks yet. Use 'add' to create one.[/yellow]")
        return

    # 필터 적용
    if status == "pending":
        tasks = [t for t in tasks if not t.get("done")]
    elif status == "done":
        tasks = [t for t in tasks if t.get("done")]

    if priority:
        tasks = [t for t in tasks if t.get("priority") == priority]

    if tag:
        tasks = [t for t in tasks if tag in t.get("tags", [])]

    if overdue:
        tasks = [t for t in tasks if is_overdue(t)]

    if not tasks:
        console.print("[yellow]No tasks match your filters.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold blue", box=None, pad_edge=False)
    table.add_column("ID", style="dim", width=4, justify="right")
    table.add_column("Task", min_width=30)
    table.add_column("Priority", width=8)
    table.add_column("Due", width=12)
    table.add_column("Tags", min_width=10)
    table.add_column("Status", width=9)

    for task in tasks:
        task_name = Text(str(task["name"]))
        if task.get("done"):
            task_name.stylize("strike dim")

        prio = task.get("priority", "medium")
        prio_colour = PRIORITY_COLOURS.get(prio, "white")
        priority_text = Text(prio, style=prio_colour)

        tags_text = Text(", ".join(task.get("tags", [])) or "—", style="dim")
        status_text = (
            Text("✓ Done", style="green") if task.get("done") else Text("Pending", style="yellow")
        )
        if is_overdue(task):
            status_text = Text("Overdue", style="bold red")

        table.add_row(
            str(task["id"]),
            task_name,
            priority_text,
            format_due(task),
            tags_text,
            status_text,
        )

    console.print(table)


@cli.command(name="search")
@click.argument("keyword", required=True)
def search_tasks(keyword: str) -> None:
    """이름 또는 설명에서 KEYWORD를 검색합니다."""
    keyword = keyword.strip()
    if not keyword:
        console.print("[red]Error: Search keyword cannot be empty.[/red]")
        sys.exit(1)

    tasks = load_tasks()
    matching_tasks = [
        task
        for task in tasks
        if keyword.casefold() in str(task.get("name", "")).casefold()
        or keyword.casefold() in str(task.get("description", "")).casefold()
    ]

    if not matching_tasks:
        console.print(Text(f"No tasks match '{keyword}'.", style="yellow"))
        return

    priority_order = {"high": 0, "medium": 1, "low": 2}
    matching_tasks.sort(key=lambda task: priority_order.get(task.get("priority"), len(priority_order)))

    table = Table(show_header=True, header_style="bold blue", box=None, pad_edge=False)
    table.add_column("ID", style="dim", width=4, justify="right")
    table.add_column("Task", min_width=30)
    table.add_column("Description", min_width=30)
    table.add_column("Priority", width=8)
    table.add_column("Status", width=9)

    for task in matching_tasks:
        priority = task.get("priority", "medium")
        priority_colour = PRIORITY_COLOURS.get(priority, "white")
        status = Text("✓ Done", style="green") if task.get("done") else Text("Pending", style="yellow")
        table.add_row(
            str(task["id"]),
            highlight_matches(str(task.get("name", "")), keyword),
            highlight_matches(str(task.get("description", "")), keyword),
            Text(priority, style=priority_colour),
            status,
        )

    console.print(table)


@cli.command()
@click.argument("task_id", type=int)
def complete(task_id: int) -> None:
    """작업을 완료로 표시합니다.

    TASK_ID는 완료 처리할 작업의 숫자 ID입니다.
    """
    repository = get_task_repository()
    task = repository.get(task_id)

    if task is None:
        console.print(f"[red]Error: No task found with ID {task_id}.[/red]")
        sys.exit(1)

    if task["done"]:
        console.print(f"[yellow]Task #{task_id} is already marked as done.[/yellow]")
        return

    task["done"] = True
    repository.update(task)
    console.print(f"[green]Task #{task_id} marked as complete.[/green]")


@cli.command()
@click.argument("task_id", type=int)
@click.option("--name", "-n", default=None, help="새 작업 이름.")
@click.option(
    "--priority",
    "-p",
    type=click.Choice(PRIORITIES),
    default=None,
    help="새 우선순위.",
)
@click.option("--description", "-d", default=None, help="새 설명.")
@click.option(
    "--due",
    default=None,
    metavar="YYYY-MM-DD",
    help="새 마감일 (삭제하려면 ''을 사용).",
)
@click.option(
    "--tag",
    "-t",
    multiple=True,
    metavar="TAG",
    help="모든 태그를 교체합니다 (여러 번 지정할 수 있으며, 생략하면 변경하지 않음).",
)
def edit(
    task_id: int,
    name: str | None,
    priority: str | None,
    description: str | None,
    due: str | None,
    tag: tuple[str, ...],
) -> None:
    """기존 작업을 수정합니다.

    TASK_ID는 수정할 작업의 숫자 ID입니다.
    """
    repository = get_task_repository()
    task = repository.get(task_id)

    if task is None:
        console.print(f"[red]Error: No task found with ID {task_id}.[/red]")
        sys.exit(1)

    changed = False

    if name is not None:
        name = name.strip()
        if not name:
            console.print("[red]Error: Task name cannot be empty.[/red]")
            sys.exit(1)
        if len(name) > 200:
            console.print("[red]Error: Task name cannot exceed 200 characters.[/red]")
            sys.exit(1)
        task["name"] = name
        changed = True

    if priority is not None:
        task["priority"] = priority
        changed = True

    if description is not None:
        task["description"] = description.strip()
        changed = True

    if due is not None:
        if due == "":
            task["due_date"] = None
        else:
            try:
                date.fromisoformat(due)
            except ValueError:
                console.print(
                    f"[red]Error: '{due}' is not a valid date. Use YYYY-MM-DD format.[/red]"
                )
                sys.exit(1)
            task["due_date"] = due
        changed = True

    if tag:
        task["tags"] = list(tag)
        changed = True

    if not changed:
        console.print("[yellow]No changes specified. Use --help to see options.[/yellow]")
        return

    repository.update(task)
    console.print(f"[green]Task #{task_id} updated.[/green]")


@cli.command()
@click.argument("task_id", type=int)
def delete(task_id: int) -> None:
    """작업을 삭제합니다.

    TASK_ID는 삭제할 작업의 숫자 ID입니다.
    """
    if not get_task_repository().delete(task_id):
        console.print(f"[red]Error: No task found with ID {task_id}.[/red]")
        sys.exit(1)

    console.print(f"[green]Task #{task_id} deleted.[/green]")


@cli.command()
def stats() -> None:
    """작업 요약을 표시합니다."""
    tasks = load_tasks()

    total = len(tasks)
    done = sum(1 for t in tasks if t.get("done"))
    pending = total - done
    overdue = sum(1 for t in tasks if is_overdue(t))

    by_priority = {p: 0 for p in PRIORITIES}
    for t in tasks:
        if not t.get("done"):
            prio = t.get("priority", "medium")
            if prio in by_priority:
                by_priority[prio] += 1

    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total tasks", str(total))
    table.add_row("[green]Done[/green]", str(done))
    table.add_row("[yellow]Pending[/yellow]", str(pending))
    table.add_row("[bold red]Overdue[/bold red]", str(overdue))
    table.add_section()
    for prio in PRIORITIES:
        colour = PRIORITY_COLOURS[prio]
        table.add_row(f"[{colour}]Pending {prio}[/{colour}]", str(by_priority[prio]))

    console.print(table)


if __name__ == "__main__":
    cli()

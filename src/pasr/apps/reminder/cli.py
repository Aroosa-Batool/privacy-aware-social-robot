"""``pasr reminder …`` commands. They write to the database directly; a running robot picks the
change up on its next scheduler poll."""

from __future__ import annotations

from typing import Annotated

import typer

from pasr.apps.reminder.service import DATE_QUESTION, ReminderError
from pasr.domain.enums import ReminderOrigin
from pasr.domain.models import Reminder
from pasr.orchestration.offline import open_offline
from pasr.settings.loader import load_settings

app = typer.Typer(help="Add, list and delete reminders.", no_args_is_help=True)


def describe(reminder: Reminder) -> str:
    badge = "sensitive" if reminder.sensitive else "not sensitive"
    return (
        f"#{reminder.id:<4} {reminder.due_at:%a %d %b %Y %H:%M}  {reminder.status.value:<13} "
        f"[{badge}] {reminder.title}"
    )


@app.command("add")
def add(
    text: Annotated[str, typer.Argument(help='e.g. "doctor appointment at 2pm tomorrow"')],
    date: Annotated[
        str | None, typer.Option(help="Answer to the date question, e.g. 'tomorrow'.")
    ] = None,
    sensitive: Annotated[
        bool | None,
        typer.Option("--sensitive/--not-sensitive", help="Override the sensitivity classifier."),
    ] = None,
) -> None:
    """Add a reminder from text. If no date is given you are asked for one."""
    offline = open_offline(load_settings(), session_id="cli")
    service = offline.service
    try:
        draft = service.draft(text)
        if draft.needs_date:
            answer = date or typer.prompt(DATE_QUESTION)
            draft = service.answer_date(draft, answer)
        reminder = service.save(draft, origin=ReminderOrigin.CLI, sensitive=sensitive)
    except ReminderError as exc:
        typer.secho(f"Not saved: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Saved {describe(reminder)}")
    if draft.time is None:
        typer.echo(f"No time given; using {reminder.due_at:%H:%M}.")


@app.command("list")
def list_reminders(
    all_: Annotated[bool, typer.Option("--all", help="Include delivered and missed.")] = False,
) -> None:
    """List reminders."""
    offline = open_offline(load_settings(), session_id="cli")
    reminders = offline.repos.reminders.all() if all_ else offline.service.upcoming()
    if not reminders:
        typer.echo("No reminders.")
    for reminder in reminders:
        typer.echo(describe(reminder))


@app.command("delete")
def delete(reminder_id: int) -> None:
    """Delete a reminder."""
    offline = open_offline(load_settings(), session_id="cli")
    if not offline.service.delete(reminder_id):
        typer.secho(f"No reminder #{reminder_id}.", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.echo(f"Deleted reminder #{reminder_id}.")

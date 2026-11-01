from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pasr.settings.loader import clear_overrides
from pasr.storage.db import Database


@dataclass(frozen=True, slots=True)
class ResetSummary:
    deleted_rows: dict[str, int]
    settings_cleared: bool


def reset(
    db: Database, data_dir: Path, *, delete_owner: bool, purge_log: bool = False
) -> ResetSummary:
    """Reset the app.

    Always deletes bystanders (with their embeddings), remembered consents and the owner's
    preferences (settings). With ``delete_owner`` it also deletes the owner , name, face and
    voice embeddings , and the owner's reminders. The research event log, which contains no
    personal content, is kept unless ``purge_log`` is set.
    """
    tables = ["consent", "bystander_embedding", "bystander"]
    if delete_owner:
        tables += ["reminder", "owner_embedding", "owner"]
    if purge_log:
        tables.append("event_log")
    deleted: dict[str, int] = {}
    with db.connect() as conn:
        for table in tables:
            deleted[table] = conn.execute(f"DELETE FROM {table}").rowcount
    db.checkpoint()
    return ResetSummary(deleted, clear_overrides(data_dir))

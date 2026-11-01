"""Every YAML file in tests/scenarios/data is a test, plus privacy invariants on what was stored."""

import sqlite3
from pathlib import Path

import pytest

from pasr.settings.schema import Settings
from pasr.storage.db import DB_FILENAME
from support.scenario import load_scenario, run_scenario, scenario_paths

PATHS = scenario_paths()


def test_scenarios_exist():
    assert len(PATHS) >= 10


@pytest.mark.parametrize("path", PATHS, ids=lambda p: p.stem)
def test_scenario(path: Path, tmp_path: Path):
    scenario = load_scenario(path)
    result = run_scenario(scenario, data_dir=tmp_path)
    failures = [f"episode {i}: {f}" for i, e in enumerate(result.episodes, 1) for f in e.failures]
    assert result.passed, "\n".join(failures)

    titles = {episode.reminder.title for episode in scenario.episodes}
    assert_only_embeddings_and_metadata_were_stored(tmp_path, titles)


@pytest.mark.parametrize("path", PATHS, ids=lambda p: p.stem)
def test_following_faces_changes_nothing_while_every_face_is_in_full_view(
    path: Path, tmp_path: Path
):
    base = Settings.model_validate({"scan": {"follow": {"enabled": True}}})
    result = run_scenario(load_scenario(path), base=base, data_dir=tmp_path)
    failures = [f"episode {i}: {f}" for i, e in enumerate(result.episodes, 1) for f in e.failures]
    assert result.passed, "\n".join(failures)


def assert_only_embeddings_and_metadata_were_stored(data_dir: Path, titles: set[str]) -> None:
    # no media or stray files next to the database
    allowed = {DB_FILENAME, f"{DB_FILENAME}-wal", f"{DB_FILENAME}-shm", ".runtime.lock"}
    assert {p.name for p in data_dir.iterdir()} <= allowed

    conn = sqlite3.connect(data_dir / DB_FILENAME)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            for row in conn.execute(f"SELECT * FROM {table}"):
                record = dict(zip(columns, row, strict=True))
                blobs = {k: v for k, v in record.items() if isinstance(v, bytes)}
                if table.endswith("_embedding"):
                    # the only binary data is a float32 vector of the declared size
                    assert set(blobs) == {"vector"}
                    assert len(blobs["vector"]) == record["dim"] * 4
                else:
                    assert not blobs, f"unexpected binary data in {table}"
                if table == "event_log":
                    text = " ".join(str(v) for v in record.values())
                    for title in titles:
                        assert title not in text, "reminder titles must not reach the event log"
    finally:
        conn.close()

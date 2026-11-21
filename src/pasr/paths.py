from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
"""Repository root (the project is always used as a source checkout)."""

OHBOT_WORK_DIR = PROJECT_ROOT / ".ohbot"
"""Working directory for the ``ohbot`` library, which writes ``ohbotData/`` into the CWD."""


def resolve(path: Path) -> Path:
    """Resolve a relative path against the project root, not the current directory."""
    return path if path.is_absolute() else PROJECT_ROOT / path

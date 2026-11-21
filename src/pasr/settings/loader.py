from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from pasr.paths import PROJECT_ROOT, resolve
from pasr.settings.schema import Settings

OVERRIDES_FILENAME = "settings.json"
ENV_PREFIX = "PASR__"
ENV_FILE = PROJECT_ROOT / ".env"


def env_layer(variables: Mapping[str, str | None]) -> dict[str, Any]:
    """``PASR__HARDWARE__OHBOT__PORT=/dev/x`` → ``{"hardware": {"ohbot": {"port": "/dev/x"}}}``.

    Values starting with ``[`` or ``{`` are parsed as YAML lists/mappings; everything else stays
    a string and is converted by validation.
    """
    layer: dict[str, Any] = {}
    for key, raw in variables.items():
        if raw is None or not key.upper().startswith(ENV_PREFIX):
            continue
        path = key[len(ENV_PREFIX) :].lower().split("__")
        value: Any = yaml.safe_load(raw) if raw.strip()[:1] in ("[", "{") else raw
        node = layer
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = value
    return layer


def environment() -> dict[str, Any]:
    """The ``.env`` file (project root) overlaid with real environment variables."""
    dotenv = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    return deep_merge(env_layer(dotenv), env_layer(os.environ))


def deep_merge(*layers: Mapping[str, Any]) -> dict[str, Any]:
    """Merge nested dicts; later layers win. Lists and scalars are replaced, not merged."""
    merged: dict[str, Any] = {}
    for layer in layers:
        for key, value in layer.items():
            if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
                merged[key] = deep_merge(merged[key], value)
            elif isinstance(value, Mapping):
                merged[key] = deep_merge(value)
            else:
                merged[key] = value
    return merged


def diff(current: Mapping[str, Any], base: Mapping[str, Any]) -> dict[str, Any]:
    """Nested dict of the leaves in ``current`` that differ from ``base``."""
    changed: dict[str, Any] = {}
    for key, value in current.items():
        other = base.get(key)
        if isinstance(value, Mapping) and isinstance(other, Mapping):
            if nested := diff(value, other):
                changed[key] = nested
        elif value != other:
            changed[key] = value
    return changed


def defaults() -> Settings:
    """Built-in defaults, ignoring the environment and any files."""
    return Settings.model_validate({})


def as_dict(settings: Settings) -> dict[str, Any]:
    return settings.model_dump(mode="json")


def read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping of settings groups")
    return data


def overrides_path(data_dir: Path) -> Path:
    return resolve(data_dir) / OVERRIDES_FILENAME


def read_overrides(data_dir: Path) -> dict[str, Any]:
    path = overrides_path(data_dir)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def write_overrides(data_dir: Path, overrides: Mapping[str, Any]) -> None:
    path = overrides_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(overrides, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def update_overrides(data_dir: Path, changes: Mapping[str, Any]) -> dict[str, Any]:
    """Merge ``changes`` into the saved overrides, dropping values equal to the defaults.

    Validates the result first so an invalid change never reaches disk.
    """
    merged = deep_merge(read_overrides(data_dir), changes)
    validated = Settings.model_validate(deep_merge(as_dict(defaults()), merged))
    pruned = diff(as_dict(validated), as_dict(defaults()))
    pruned.get("storage", {}).pop("data_dir", None)  # the data dir cannot live inside itself
    if pruned.get("storage") == {}:
        del pruned["storage"]
    write_overrides(data_dir, pruned)
    return pruned


def clear_overrides(data_dir: Path) -> bool:
    path = overrides_path(data_dir)
    if path.exists():
        path.unlink()
        return True
    return False


def load_settings(
    *,
    data_dir: Path | None = None,
    profile: Path | None = None,
    explicit: Mapping[str, Any] | None = None,
    use_environment: bool = True,
) -> Settings:
    """Effective settings: defaults < profile < saved overrides < ``.env`` < environment
    < ``explicit`` (command-line flags). ``data_dir`` wins over every layer.

    The defaults are merged in as a real layer (not left to field defaults) because the saved
    overrides are pruned to changed leaves: a plugin choice whose params changed is stored
    without its ``plugin``, which is required."""
    base = as_dict(defaults())
    profile_layer = read_yaml(profile) if profile else {}
    env = environment() if use_environment else {}
    outer = deep_merge(env, explicit or {})  # layers that may choose the data directory
    located = Settings.model_validate(deep_merge(base, profile_layer, outer))
    resolved_dir = resolve(data_dir or located.storage.data_dir)
    return Settings.model_validate(
        deep_merge(
            base,
            profile_layer,
            read_overrides(resolved_dir),
            outer,
            {"storage": {"data_dir": str(resolved_dir)}},
        )
    )


def dump_yaml(settings: Settings, *, exclude_paths: bool = True) -> str:
    data = as_dict(settings)
    if exclude_paths:
        data["storage"].pop("data_dir", None)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from pasr.paths import PROJECT_ROOT
from pasr.perception import registry
from pasr.settings import loader
from pasr.settings.loader import (
    as_dict,
    defaults,
    dump_yaml,
    env_layer,
    load_settings,
    read_overrides,
    update_overrides,
)
from pasr.settings.schema import Settings
from pasr.settings.tiers import field_tier, visible


def leaf_fields(model: type[BaseModel], prefix=""):
    for name, field in model.model_fields.items():
        annotation = field.annotation
        is_group = (
            isinstance(annotation, type)
            and issubclass(annotation, BaseModel)
            and field.json_schema_extra is None
        )
        if is_group:
            yield from leaf_fields(annotation, f"{prefix}{name}.")
        else:
            yield f"{prefix}{name}", field


def test_every_setting_has_a_tier():
    missing = [name for name, field in leaf_fields(Settings) if field_tier(field) is None]
    assert missing == []


def test_every_plugin_parameter_has_a_tier():
    for spec in registry.specs():
        if spec.available:
            params = registry.load_class(spec).Params
            missing = [n for n, f in leaf_fields(params) if field_tier(f) is None]
            assert missing == [], f"{spec.kind}/{spec.name}"


def test_tiers_nest():
    fields = dict(leaf_fields(Settings))
    modality = fields["privacy.detection_modality"]
    threshold = fields["identity.voice_threshold"]
    assert visible(modality, "basic")
    assert not visible(threshold, "basic")
    assert visible(threshold, "advanced")


def test_reference_yaml_matches_the_defaults():
    reference = PROJECT_ROOT / "config" / "default.yaml"
    assert reference.read_text(encoding="utf-8") == dump_yaml(defaults()), (
        "regenerate with: uv run pasr config dump --defaults > config/default.yaml"
    )


@pytest.mark.parametrize(
    "profile", sorted((PROJECT_ROOT / "config" / "profiles").glob("*.yaml")), ids=lambda p: p.stem
)
def test_example_profiles_are_valid(profile: Path, tmp_path: Path):
    load_settings(data_dir=tmp_path, profile=profile)


def test_unknown_plugins_and_keys_are_rejected():
    with pytest.raises(ValidationError):
        Settings.model_validate({"perception": {"face": {"plugin": "nope"}}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"privacy": {"typo": 1}})


def test_layering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    profile = tmp_path / "profile.yaml"
    profile.write_text("reminder: {wake_lead_minutes: 3, listen_window_minutes: 2}\n")
    update_overrides(
        data, {"reminder": {"wake_lead_minutes": 4}, "consent": {"timeout_seconds": 9}}
    )
    monkeypatch.setenv("PASR__CONSENT__TIMEOUT_SECONDS", "11")
    monkeypatch.setenv("PASR__SCAN__POSITIONS", "[front]")

    settings = load_settings(
        data_dir=data, profile=profile, explicit={"hardware": {"camera": {"index": 3}}}
    )

    assert settings.reminder.listen_window_minutes == 2  # profile
    assert settings.reminder.wake_lead_minutes == 4  # overrides beat the profile
    assert settings.consent.timeout_seconds == 11  # environment beats overrides
    assert [d.value for d in settings.scan.positions] == ["front"]
    assert settings.hardware.camera.index == 3  # explicit flags beat everything
    assert settings.storage.data_dir == data


def test_dotenv_file_is_read_and_environment_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "PASR__CONSENT__TIMEOUT_SECONDS=20\nPASR__IDENTITY__ENROLL_FACE_SAMPLES=2\n"
    )
    monkeypatch.setattr(loader, "ENV_FILE", env_file)
    monkeypatch.setenv("PASR__IDENTITY__ENROLL_FACE_SAMPLES", "4")
    settings = load_settings(data_dir=tmp_path / "data")
    assert settings.consent.timeout_seconds == 20
    assert settings.identity.enroll_face_samples == 4


def test_env_layer_parsing():
    layer = env_layer({"PASR__A__B": "x", "PASR__C": "[1, 2]", "OTHER": "y", "PASR__D": None})
    assert layer == {"a": {"b": "x"}, "c": [1, 2]}


def test_overrides_keep_only_changes_and_never_store_invalid_values(tmp_path: Path):
    data = tmp_path / "data"
    update_overrides(data, {"reminder": {"wake_lead_minutes": 9}})
    update_overrides(data, {"reminder": {"wake_lead_minutes": 7.0}})  # back to the default
    assert read_overrides(data) == {}
    update_overrides(data, {"consent": {"timeout_seconds": 5}})
    with pytest.raises(ValidationError):
        update_overrides(data, {"consent": {"timeout_seconds": -1}})
    assert json.loads((data / "settings.json").read_text()) == {"consent": {"timeout_seconds": 5.0}}


def test_overridden_plugin_params_keep_the_default_plugin(tmp_path: Path):
    data = tmp_path / "data"
    topics = ["a password or a PIN"]
    params = {"sensitive_topics": topics}
    update_overrides(data, {"perception": {"sensitivity": {"params": params}}})
    assert "plugin" not in read_overrides(data)["perception"]["sensitivity"]  # pruned as a default
    sensitivity = load_settings(data_dir=data).perception.sensitivity
    assert sensitivity.plugin == "zero_shot"
    assert sensitivity.params == params


def test_profile_round_trip(tmp_path: Path):
    changed = Settings.model_validate({"privacy": {"disclosure_policy": "always_disclose"}})
    profile = tmp_path / "p.yaml"
    profile.write_text(dump_yaml(changed))
    loaded = load_settings(data_dir=tmp_path / "data", profile=profile)
    assert as_dict(loaded)["privacy"] == as_dict(changed)["privacy"]

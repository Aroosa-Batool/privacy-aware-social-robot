import pytest

from pasr.perception import registry
from pasr.perception.registry import (
    PluginKind,
    PluginSpec,
    PluginUnavailableError,
    UnknownPluginError,
)
from pasr.settings.schema import PerceptionSettings


def test_every_kind_defaults_to_a_real_plugin():
    defaults = PerceptionSettings()
    for kind in PluginKind:
        spec = registry.get_spec(kind, defaults.choice(kind).plugin)
        assert spec.target is not None and spec.target.startswith("pasr."), spec
        assert spec.available, spec  # its libraries are core dependencies


@pytest.mark.parametrize("spec", [s for s in registry.specs() if s.available], ids=str)
def test_available_plugins_build_with_default_params(spec: PluginSpec):
    plugin = registry.create(spec.kind, spec.name)
    assert isinstance(plugin, registry.load_class(spec))


@pytest.mark.parametrize("spec", [s for s in registry.specs() if s.requires and s.target], ids=str)
def test_status_follows_the_installed_libraries(spec: PluginSpec):
    missing = spec.missing_dependencies
    if missing:
        assert spec.status == "missing " + ", ".join(missing)
        with pytest.raises(PluginUnavailableError, match="needs"):
            registry.create(spec.kind, spec.name)
    else:
        assert spec.status == "available"


def test_planned_plugins_are_listed_but_not_creatable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(registry, "_CATALOG", list(registry.specs()))
    registry.register(PluginSpec(PluginKind.STT, "future", "not built yet", None, (), "M5"))
    spec = registry.get_spec(PluginKind.STT, "future")
    assert not spec.available
    assert spec.status == "planned (M5)"
    with pytest.raises(PluginUnavailableError):
        registry.create(PluginKind.STT, "future")


def test_unknown_plugin():
    with pytest.raises(UnknownPluginError):
        registry.get_spec(PluginKind.VAD, "nope")


def test_register_adds_or_replaces(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(registry, "_CATALOG", list(registry.specs()))
    spec = PluginSpec(PluginKind.VAD, "energy2", "copy", "pasr.perception.vad.energy:EnergyVAD")
    registry.register(spec)
    registry.register(spec)
    assert [s.name for s in registry.specs(PluginKind.VAD)].count("energy2") == 1
    assert (
        registry.create(PluginKind.VAD, "energy2", {"rms_threshold": 0.1}).params.rms_threshold
        == 0.1
    )

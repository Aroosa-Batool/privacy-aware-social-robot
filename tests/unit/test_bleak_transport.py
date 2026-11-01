import pytest

from fakes import BLEDevice, FakeBleak
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.hardware.watch.bangle import NUS_RX, NUS_TX, BangleWatch, BleakTransport


def transport(**kwargs) -> BleakTransport:
    defaults = dict(name_prefix="Bangle.js", address=None, reconnect_attempts=2)
    return BleakTransport(**{**defaults, **kwargs})


async def test_scans_by_name_and_caches_the_address(monkeypatch):
    world = FakeBleak().install(monkeypatch)
    found = []
    t = transport(on_address_found=found.append)
    await t.connect(lambda data: None)
    assert t.is_connected and found == ["UUID-1"] and world.scans == [("filter", None)]
    assert world.clients[0].notify_uuid == NUS_TX


async def test_cached_address_is_tried_first_then_scan(monkeypatch):
    world = FakeBleak([BLEDevice("Bangle.js 9f", "UUID-NEW")]).install(monkeypatch)
    found = []
    t = transport(address="UUID-OLD", on_address_found=found.append)
    await t.connect(lambda data: None)
    assert world.scans == [("address", "UUID-OLD"), ("filter", None)]
    assert found == ["UUID-NEW"] and t.address == "UUID-NEW"


async def test_retries_then_gives_up(monkeypatch):
    world = FakeBleak().install(monkeypatch)
    world.connect_failures = 2
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    await transport(reconnect_attempts=2).connect(lambda data: None)
    assert world.connects == 1

    world.connect_failures = 5
    with pytest.raises(HardwareNotAvailableError, match="after 3 attempt"):
        await transport(reconnect_attempts=2).connect(lambda data: None)

    FakeBleak([]).install(monkeypatch)
    with pytest.raises(HardwareNotAvailableError, match="load bangle/consent_app.js"):
        await transport(reconnect_attempts=0).connect(lambda data: None)


async def test_bluetooth_off_is_not_retried(monkeypatch):
    world = FakeBleak(bluetooth_off=True).install(monkeypatch)
    with pytest.raises(HardwareNotAvailableError, match="Bluetooth is off"):
        await transport().connect(lambda data: None)
    assert len(world.scans) == 1


async def test_drop_flips_is_connected_and_write_needs_a_link(monkeypatch):
    world = FakeBleak().install(monkeypatch)
    t = transport()
    with pytest.raises(HardwareNotAvailableError):
        await t.write(b"x")
    await t.connect(lambda data: None)
    await t.write(b"x")
    assert world.write_uuid == NUS_RX
    world.clients[0].drop()
    assert not t.is_connected
    await t.disconnect()


async def test_bangle_watch_round_trips_over_the_transport(monkeypatch):
    world = FakeBleak().install(monkeypatch)
    watch = BangleWatch(transport())
    assert await watch.ping()
    world.clients[0].drop()  # the watch slept; the next request reconnects
    await watch.notify("Reminder: Dentist")
    assert world.connects == 2
    assert b"".join(world.clients[1].written).startswith(b"\x10notify(")


async def _no_sleep(seconds: float) -> None:
    return None


async def test_missing_library(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "bleak", None)
    with pytest.raises(HardwareNotAvailableError, match="bleak library is not installed: uv sync"):
        await transport().connect(lambda data: None)


async def test_closed_app_is_detected_without_logging_the_echoed_command(monkeypatch, caplog):
    """With the app closed, Espruino echoes the failed command , which may hold a reminder
    title , next to the error. The watch flags the missing app and logs no console text."""
    world = FakeBleak().install(monkeypatch)
    watch = BangleWatch(transport(), reply_margin_s=0.05)
    await watch.connect()
    console = (
        b'>Uncaught ReferenceError: "notify" is not defined\r\n'
        b' at line 1 col 1\r\nnotify("Reminder: Dentist");Bluetooth.println("NOTIFIED:1")\r\n^\r\n>'
    )
    with caplog.at_level("DEBUG", logger="pasr.hardware.watch.bangle"):
        world.clients[0]._on_notify(None, bytearray(console))
    assert watch.app_missing
    assert "Dentist" not in caplog.text
    await watch.disconnect()

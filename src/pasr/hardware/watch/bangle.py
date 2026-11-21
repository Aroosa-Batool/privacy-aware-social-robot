"""Bangle.js watch: request/response logic over a pluggable byte transport.

The protocol logic is tested against an emulation of ``bangle/consent_app.js``; ``BleakTransport``
carries it over the Nordic UART Service.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Callable
from typing import Any, Protocol

from pasr.domain.enums import WatchAnswer
from pasr.hardware.protocols import HardwareNotAvailableError
from pasr.hardware.watch.protocol import (
    LineDecoder,
    WatchReply,
    chunks,
    consent_command,
    notify_command,
    parse_reply,
    ping_command,
)

logger = logging.getLogger(__name__)

NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
"""The PC writes here."""
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
"""The PC subscribes to notifications here."""

APP_MISSING_MARKERS = ('"consent" is not defined', '"notify" is not defined')
"""What the Espruino console prints when a command arrives while the app is not loaded."""


class WatchTransport(Protocol):
    @property
    def is_connected(self) -> bool: ...

    async def connect(self, on_data: Callable[[bytes], None]) -> None: ...

    async def write(self, data: bytes) -> None: ...

    async def disconnect(self) -> None: ...


class BleakTransport:
    """Nordic UART over BLE with ``bleak``.

    macOS identifies devices by a CoreBluetooth UUID, so the watch is found by name prefix and
    the UUID is handed to ``on_address_found`` for caching in settings. Bangle.js 1 drops the
    link when it sleeps; the disconnect callback clears the client so ``is_connected`` is
    truthful and ``BangleWatch`` reconnects before its next request.
    """

    def __init__(
        self,
        name_prefix: str,
        address: str | None,
        reconnect_attempts: int,
        *,
        scan_timeout_s: float = 10.0,
        connect_timeout_s: float = 20.0,
        on_address_found: Callable[[str], None] | None = None,
    ) -> None:
        self.name_prefix = name_prefix
        self.address = address
        self.reconnect_attempts = reconnect_attempts
        self.scan_timeout_s = scan_timeout_s
        self.connect_timeout_s = connect_timeout_s
        self.on_address_found = on_address_found
        self._client: Any = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and bool(self._client.is_connected)

    async def connect(self, on_data: Callable[[bytes], None]) -> None:
        try:
            import bleak
            import bleak.exc
        except ImportError as exc:
            raise HardwareNotAvailableError("The bleak library is not installed: uv sync") from exc
        unavailable: tuple[type[BaseException], ...] = tuple(
            cls
            for cls in (getattr(bleak.exc, "BleakBluetoothNotAvailableError", None),)
            if cls is not None
        )
        attempts = self.reconnect_attempts + 1
        last: BaseException | None = None
        for attempt in range(attempts):
            try:
                device = await self._find(bleak)
                if device is None:
                    raise HardwareNotAvailableError(
                        f"no Bluetooth device named {self.name_prefix}* found; "
                        "load bangle/consent_app.js on the watch"
                    )
                await self._open(bleak, device, on_data)
                return
            except unavailable as exc:
                raise HardwareNotAvailableError(
                    "Bluetooth is off, or this terminal has no Bluetooth permission"
                ) from exc
            except (bleak.exc.BleakError, HardwareNotAvailableError, TimeoutError, OSError) as exc:
                last = exc
                await self.disconnect()
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.5 * 2**attempt)
        raise HardwareNotAvailableError(
            f"could not connect to the watch after {attempts} attempt(s): {last}"
        )

    async def write(self, data: bytes) -> None:
        if not self.is_connected:
            raise HardwareNotAvailableError("the watch is not connected")
        await self._client.write_gatt_char(NUS_RX, data, response=False)

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                logger.debug("watch disconnect failed", exc_info=True)

    # --- the only code that talks to bleak ----------------------------------------------

    async def _find(self, bleak: Any) -> Any:
        device = None
        if self.address:
            device = await bleak.BleakScanner.find_device_by_address(
                self.address, timeout=self.scan_timeout_s
            )
        if device is None:
            prefix = self.name_prefix
            device = await bleak.BleakScanner.find_device_by_filter(
                lambda d, _adv: str(d.name or "").startswith(prefix), timeout=self.scan_timeout_s
            )
        if device is not None and device.address != self.address:
            self.address = device.address
            if self.on_address_found is not None:
                self.on_address_found(str(device.address))
        return device

    async def _open(self, bleak: Any, device: Any, on_data: Callable[[bytes], None]) -> None:
        client = bleak.BleakClient(
            device, disconnected_callback=self._on_disconnect, timeout=self.connect_timeout_s
        )
        await client.connect()
        await client.start_notify(NUS_TX, lambda _sender, data: on_data(bytes(data)))
        self._client = client

    def _on_disconnect(self, client: Any) -> None:
        if client is self._client:
            self._client = None


class BangleWatch:
    """The ``Watch`` protocol on top of a ``WatchTransport``."""

    def __init__(self, transport: WatchTransport, *, reply_margin_s: float = 5.0) -> None:
        self.transport = transport
        self.reply_margin_s = reply_margin_s
        self._ids = itertools.count(1)
        self._decoder = LineDecoder()
        self._waiting: dict[int, asyncio.Future[WatchReply]] = {}
        self.app_missing = False
        """Set when the console shows that the consent app is not loaded."""

    @property
    def is_connected(self) -> bool:
        return self.transport.is_connected

    async def connect(self) -> None:
        await self.transport.connect(self._on_data)

    async def disconnect(self) -> None:
        await self.transport.disconnect()

    async def prompt(self, text: str, timeout_s: float) -> WatchAnswer:
        """The app dismisses an unanswered prompt itself and sends nothing: that is TIMEOUT."""
        reply = await self._request(
            lambda request_id: consent_command(request_id, text, timeout_s),
            timeout_s + self.reply_margin_s,
        )
        if reply is None or reply.value not in ("yes", "no"):
            return WatchAnswer.TIMEOUT
        return WatchAnswer(reply.value)

    async def notify(self, text: str) -> None:
        reply = await self._request(
            lambda request_id: notify_command(request_id, text), self.reply_margin_s
        )
        if reply is None:
            raise HardwareNotAvailableError(
                "the watch did not show the reminder; is bangle/consent_app.js loaded?"
            )

    async def ping(self) -> bool:
        """True when the watch answers and the consent app is loaded."""
        reply = await self._request(ping_command, self.reply_margin_s)
        if reply is None:
            return False
        self.app_missing = reply.value != "function"
        return not self.app_missing

    async def _request(
        self, command: Callable[[int], bytes], timeout_s: float
    ) -> WatchReply | None:
        if not self.transport.is_connected:
            await self.connect()
        request_id = next(self._ids)
        future: asyncio.Future[WatchReply] = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future
        try:
            for piece in chunks(command(request_id)):
                await self.transport.write(piece)
            return await asyncio.wait_for(future, timeout=timeout_s)
        except TimeoutError:
            return None
        finally:
            self._waiting.pop(request_id, None)

    def _on_data(self, data: bytes) -> None:
        for line in self._decoder.feed(data):
            reply = parse_reply(line)
            if reply is None:
                # Console output is never logged verbatim: on errors Espruino echoes the failed
                # command, which can contain a reminder title.
                if any(marker in line for marker in APP_MISSING_MARKERS):
                    self.app_missing = True
                    logger.warning("the consent app is not loaded on the watch")
                elif line.strip():
                    logger.debug("ignoring %d characters of watch console output", len(line))
                continue
            if reply.type != "pong":
                self.app_missing = False
            future = self._waiting.get(reply.id)
            if future is not None and not future.done():
                future.set_result(reply)

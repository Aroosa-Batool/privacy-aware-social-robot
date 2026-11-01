"""Stand-ins for hardware/ML libraries, installed into ``sys.modules`` by tests so the adapters
run in CI without the real packages."""

from __future__ import annotations

import asyncio
import importlib.abc
import importlib.machinery
import json
import re
import sys
import threading
import types
from pathlib import Path
from typing import Any

import pytest


class FakeOhbot(types.ModuleType):
    """Mimics ``ohbot.ohbot`` (the package's ``__init__`` is empty): probes at import, records
    calls, writes the speech file, and asserts that no two calls overlap (the real library is
    not thread-safe)."""

    def __init__(self, *, connected: bool = True, answering: tuple[str, ...] = ()) -> None:
        super().__init__("ohbot.ohbot")
        self.connected = connected
        self.port = ""
        self.answering = answering
        """Ports that answer the version query when ``init`` is called with a port."""
        self.import_cwd: Path | None = None
        self.init_ports: list[str | None] = []
        self.probed: list[str] = []
        self.default_played: list[str] = []
        self.calls: list[tuple[Any, ...]] = []
        self._busy = threading.Lock()

    def _call(self, *call: Any) -> None:
        if not self._busy.acquire(blocking=False):
            raise AssertionError(f"concurrent ohbot call: {call}")
        try:
            self.calls.append(call)
        finally:
            self._busy.release()

    def init(self, portName: str | None = None) -> None:  # noqa: N803 - library spelling
        self.init_ports.append(portName)
        if portName is not None:
            device = portName[0]  # the real checkPort opens p[0], meant for a ListPortInfo
            self.probed.append(device)
            if device in self.answering:
                self.connected, self.port = True, portName

    def move(self, m: int, pos: float, spd: int = 5, eye: int = 0) -> None:
        self._call("move", m, pos, spd)

    def say(self, text: str, untilDone: bool = True, lipSync: bool = True) -> None:  # noqa: N803
        # Like `say -o ohbotData/ohbotspeech.wav` + wave.open: relative to the CWD, and the
        # folder is not created here (only at import). Playback goes through the module-level
        # `playsound`, as in the real _playSpeech thread.
        Path("ohbotData/ohbotspeech.wav").write_bytes(b"RIFF")
        self._call("say", text)
        self.playsound("ohbotData/ohbotspeech.wav")

    def playsound(self, sound: str, block: bool = True) -> None:
        self.default_played.append(sound)

    def close(self) -> None:
        self._call("close")


class _ModuleFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Serves fixed module objects by name; calls ``on_import`` when one is first created."""

    def __init__(self, modules: dict[str, types.ModuleType], on_import: Any = None) -> None:
        self.modules = modules
        self.on_import = on_import

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        module = self.modules.get(fullname)
        if module is None:
            return None
        is_package = hasattr(module, "__path__")
        return importlib.machinery.ModuleSpec(fullname, self, is_package=is_package)

    def create_module(self, spec: Any) -> types.ModuleType:
        if self.on_import is not None:
            self.on_import(spec.name)
        return self.modules[spec.name]

    def exec_module(self, module: types.ModuleType) -> None:
        pass


def install_fake_ohbot(
    monkeypatch: pytest.MonkeyPatch, *, connected: bool = True, answering: tuple[str, ...] = ()
) -> FakeOhbot:
    """Make ``from ohbot import ohbot`` yield a fresh fake (inside an empty ``ohbot`` package,
    like the real one) and record the CWD when the submodule is imported."""
    fake = FakeOhbot(connected=connected, answering=answering)
    package = types.ModuleType("ohbot")
    package.__path__ = []  # type: ignore[attr-defined]

    def on_import(name: str) -> None:
        if name == "ohbot.ohbot":
            fake.import_cwd = Path.cwd()
            Path("ohbotData").mkdir(exist_ok=True)  # module-level setup, relative to the CWD

    for name in ("ohbot", "ohbot.ohbot"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    finder = _ModuleFinder({"ohbot": package, "ohbot.ohbot": fake}, on_import)
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
    return fake


# --- bleak -----------------------------------------------------------------------------


class BleakError(Exception):
    pass


class BleakBluetoothNotAvailableError(BleakError):
    pass


class ConsentAppConsole:
    """The Espruino console with ``bangle/consent_app.js`` loaded (or not): evaluates the
    command lines the PC sends and returns what the watch prints. The real app is also run under
    Node against the same commands (tests/unit/test_consent_app_js.py)."""

    CONSENT = re.compile(r'^consent\("(\d+)",(".*"),(\d+)\)$')
    NOTIFY = re.compile(r'^notify\((".*")\);Bluetooth\.println\("NOTIFIED:(\d+)"\)$')
    PING = re.compile(r'^Bluetooth\.println\("PONG:(\d+):"\+typeof consent\)$')

    def __init__(self, answer: str | None = "YES", *, loaded: bool = True) -> None:
        self.answer = answer
        """``YES``/``NO``; ``None`` leaves prompts unanswered (the app then sends nothing)."""
        self.loaded = loaded
        self.received: list[tuple[str, ...]] = []

    def evaluate(self, line: bytes) -> list[str]:
        assert line.startswith(b"\x10"), "commands must not be echoed"
        code = line[1:].decode("ascii")  # the PC sends ASCII-only JavaScript
        if match := self.PING.match(code):
            self.received.append(("ping",))
            return [f"PONG:{match[1]}:{'function' if self.loaded else 'undefined'}"]
        name = (
            "consent" if self.CONSENT.match(code) else "notify" if self.NOTIFY.match(code) else None
        )
        assert name is not None, f"unexpected command: {code!r}"
        if not self.loaded:
            return [f'Uncaught ReferenceError: "{name}" is not defined', " at line 1 col 1", code]
        if match := self.CONSENT.match(code):
            self.received.append(("consent", json.loads(match[2]), int(match[3])))
            return [f"CONSENT:{match[1]}:{self.answer}"] if self.answer else []
        match = self.NOTIFY.match(code)
        assert match is not None
        self.received.append(("notify", json.loads(match[1])))
        return [f"NOTIFIED:{match[2]}"]


class BLEDevice:
    def __init__(self, name: str, address: str) -> None:
        self.name = name
        self.address = address


class FakeBleakClient:
    """Emulates the watch end of the Nordic UART link, running ``ConsentAppConsole``."""

    def __init__(
        self,
        device: BLEDevice,
        *,
        world: FakeBleak,
        disconnected_callback: Any = None,
        timeout: float = 10.0,
    ) -> None:
        self.device = device
        self.world = world
        self.disconnected_callback = disconnected_callback
        self.timeout = timeout
        self.is_connected = False
        self.notify_uuid: str | None = None
        self._on_notify: Any = None
        self._buffer = b""
        self.written: list[bytes] = []

    async def connect(self) -> None:
        if self.world.connect_failures > 0:
            self.world.connect_failures -= 1
            raise BleakError("connection failed")
        self.is_connected = True
        self.world.connects += 1
        self.world.clients.append(self)

    async def disconnect(self) -> None:
        self.is_connected = False

    def drop(self) -> None:
        """The watch went to sleep."""
        self.is_connected = False
        if self.disconnected_callback is not None:
            self.disconnected_callback(self)

    async def start_notify(self, uuid: str, callback: Any) -> None:
        self.notify_uuid = uuid
        self._on_notify = callback

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = True) -> None:
        assert not response and len(data) <= 20
        self.world.write_uuid = uuid
        self.written.append(bytes(data))
        self._buffer += bytes(data)
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            output = self.world.console.evaluate(line)
            asyncio.get_running_loop().call_soon(self._print, output)

    def _print(self, output: list[str]) -> None:
        data = "".join(f"{line}\r\n" for line in output).encode()
        for i in range(0, len(data), 7):  # notifications arrive fragmented
            self._on_notify(None, bytearray(data[i : i + 7]))


class FakeBleak:
    """Builds a ``bleak`` module whose scanner finds ``devices`` and whose clients talk back."""

    def __init__(
        self, devices: list[BLEDevice] | None = None, *, bluetooth_off: bool = False
    ) -> None:
        self.devices = devices if devices is not None else [BLEDevice("Bangle.js 1a2b", "UUID-1")]
        self.bluetooth_off = bluetooth_off
        self.connect_failures = 0
        self.connects = 0
        self.scans: list[tuple[str, Any]] = []
        self.clients: list[FakeBleakClient] = []
        self.write_uuid: str | None = None
        self.console = ConsentAppConsole()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> FakeBleak:
        world = self

        class BleakScanner:
            @classmethod
            async def find_device_by_address(cls, address: str, **kwargs: Any) -> Any:
                world.scans.append(("address", address))
                world._check_radio()
                return next((d for d in world.devices if d.address == address), None)

            @classmethod
            async def find_device_by_filter(cls, filterfunc: Any, **kwargs: Any) -> Any:
                world.scans.append(("filter", None))
                world._check_radio()
                return next((d for d in world.devices if filterfunc(d, None)), None)

        class BleakClient(FakeBleakClient):
            def __init__(self, device: BLEDevice, **kwargs: Any) -> None:
                super().__init__(device, world=world, **kwargs)

        exc = types.ModuleType("bleak.exc")
        exc.BleakError = BleakError  # type: ignore[attr-defined]
        exc.BleakBluetoothNotAvailableError = BleakBluetoothNotAvailableError  # type: ignore[attr-defined]
        module = types.ModuleType("bleak")
        module.exc = exc  # type: ignore[attr-defined]
        module.BleakScanner = BleakScanner  # type: ignore[attr-defined]
        module.BleakClient = BleakClient  # type: ignore[attr-defined]
        module.BleakError = BleakError  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "bleak", module)
        monkeypatch.setitem(sys.modules, "bleak.exc", exc)
        return self

    def _check_radio(self) -> None:
        if self.bluetooth_off:
            raise BleakBluetoothNotAvailableError("Bluetooth is off")


# --- cv2 -----------------------------------------------------------------------------------


class FakeCv2:
    """Builds a ``cv2`` module: ``VideoCapture`` opens the listed indices, ``imread`` serves the
    given images (BGR arrays keyed by file name) and ``None`` for anything else."""

    CAP_ANY = 0
    CAP_AVFOUNDATION = 1200
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4

    def __init__(
        self,
        *,
        open_indices: tuple[int, ...] = (0,),
        images: dict[str, Any] | None = None,
        size: tuple[int, int] = (480, 640),
        fail_reads_after: int | None = None,
        stalls: dict[int, range] | None = None,
    ) -> None:
        self.open_indices = open_indices
        self.images = images or {}
        self.size = size
        self.fail_reads_after = fail_reads_after
        self.stalls = stalls or {}
        """Reads (numbered from 1) that fail, by capture (the n-th ``VideoCapture`` made)."""
        self.captures: list[Any] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> FakeCv2:
        monkeypatch.setitem(sys.modules, "cv2", self.module())
        return self

    def module(self) -> types.ModuleType:
        """The module, for ``sys.modules["cv2"]`` (a camera helper process sets it itself)."""
        import numpy as np

        world = self

        class VideoCapture:
            def __init__(self, index: int, backend: int = 0) -> None:
                self.index, self.backend = index, backend
                self.props: dict[int, float] = {}
                self.reads = 0
                self.released = False
                self.stalled = world.stalls.get(len(world.captures), range(0))
                world.captures.append(self)

            def isOpened(self) -> bool:  # noqa: N802 - OpenCV spelling
                return self.index in world.open_indices

            def set(self, prop: int, value: float) -> bool:
                self.props[prop] = value
                return True

            def get(self, prop: int) -> float:
                return self.props.get(prop, 0.0)

            def read(self) -> tuple[bool, Any]:
                self.reads += 1
                if world.fail_reads_after is not None and self.reads > world.fail_reads_after:
                    return False, None
                if self.reads in self.stalled:
                    return False, None
                return True, np.full((*world.size, 3), self.reads, dtype=np.uint8)

            def release(self) -> None:
                self.released = True

        module = types.ModuleType("cv2")
        for name in (
            "CAP_ANY",
            "CAP_AVFOUNDATION",
            "CAP_PROP_FRAME_WIDTH",
            "CAP_PROP_FRAME_HEIGHT",
        ):
            setattr(module, name, getattr(FakeCv2, name))
        module.VideoCapture = VideoCapture  # type: ignore[attr-defined]
        module.imread = lambda path: world.images.get(Path(path).name)  # type: ignore[attr-defined]
        return module


class FakeCameraHelpers:
    """Camera helper processes that run the real helper with a stand-in cv2
    (``support/camera_helper.py``). ``plan`` sets up the 1st, 2nd, … helper started, the last
    one for any after it: FakeCv2 settings, plus ``cameras`` (names by index, by default only
    the C615), ``missing`` (no OpenCV), ``stalled_reads`` [first, stop) and ``exit_at_read``
    (the helper dies there)."""

    SCRIPT = Path(__file__).parent / "support" / "camera_helper.py"

    def __init__(self, folder: Path) -> None:
        self.plan_file = folder / "camera-plan.json"
        self.command = (sys.executable, str(self.SCRIPT), str(self.plan_file))
        self.plan({})

    def plan(self, *starts: dict[str, Any]) -> None:
        self.plan_file.write_text(json.dumps(starts))

    @property
    def started(self) -> int:
        counter = self.plan_file.with_suffix(".starts")
        return int(counter.read_text()) if counter.exists() else 0

    def report(self, number: int) -> list[dict[str, Any]] | None:
        """The captures the ``number``-th helper (from 0) made, as it ended; ``None`` if it was
        killed or died."""
        path = self.plan_file.with_suffix(f".{number}.json")
        return json.loads(path.read_text()) if path.exists() else None


# --- sounddevice / soundfile ---------------------------------------------------------------


class FakeSoundDevice:
    """Builds a ``sounddevice`` module whose ``InputStream`` fires ``chunks`` callbacks from a
    background thread, the ``overflow_at``-th one flagged as an input overflow."""

    def __init__(
        self,
        *,
        chunks: int = 6,
        overflow_at: int | None = None,
        bad_devices: tuple[str, ...] = (),
        failing_opens: int = 0,
    ) -> None:
        self.chunks = chunks
        self.overflow_at = overflow_at
        self.bad_devices = bad_devices
        self.failing_opens = failing_opens
        """The first N streams fail to open, whatever the device (a headset switching mode)."""
        self.opens = 0
        self.streams: list[Any] = []
        self.played: list[tuple[Any, int, Any]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> FakeSoundDevice:
        import numpy as np

        world = self

        class Status:
            def __init__(self, overflow: bool) -> None:
                self.input_overflow = overflow

            def __bool__(self) -> bool:
                return self.input_overflow

        class PortAudioError(Exception):
            pass

        class InputStream:
            def __init__(
                self,
                *,
                samplerate: int,
                channels: int,
                dtype: str,
                blocksize: int,
                device: Any,
                callback: Any,
            ) -> None:
                world.opens += 1
                if device in world.bad_devices or world.opens <= world.failing_opens:
                    raise PortAudioError("Error opening InputStream: Internal PortAudio error")
                self.samplerate, self.channels, self.dtype = samplerate, channels, dtype
                self.blocksize, self.device, self.callback = blocksize, device, callback
                self.started = self.stopped = self.closed = False
                self._thread: threading.Thread | None = None
                world.streams.append(self)

            def start(self) -> None:
                self.started = True

                def run() -> None:
                    for i in range(world.chunks):
                        if self.stopped:
                            return
                        frames = np.full((self.blocksize, 1), 0.01 * (i + 1), dtype=np.float32)
                        self.callback(frames, self.blocksize, None, Status(i == world.overflow_at))

                self._thread = threading.Thread(target=run, daemon=True)
                self._thread.start()

            def stop(self) -> None:
                """Like PortAudio: no callback runs once ``stop`` has returned."""
                self.stopped = True
                if self._thread is not None:
                    self._thread.join()

            def close(self) -> None:
                self.closed = True

        module = types.ModuleType("sounddevice")
        module.InputStream = InputStream  # type: ignore[attr-defined]
        module.PortAudioError = PortAudioError  # type: ignore[attr-defined]
        devices = [
            {"name": "MacBook Air Microphone", "max_input_channels": 1, "max_output_channels": 0},
            {"name": "MacBook Air Speakers", "max_input_channels": 0, "max_output_channels": 2},
            {"name": "USB Audio", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "AirPods Pro", "max_input_channels": 1, "max_output_channels": 2},
        ]

        def query_devices(device: Any = None, kind: str | None = None) -> Any:
            if kind == "input":  # the default input: AirPods, as on the owner's Mac
                return devices[3]
            return devices

        module.query_devices = query_devices  # type: ignore[attr-defined]

        def play(data: Any, samplerate: int, device: Any = None, blocking: bool = False) -> None:
            assert blocking
            world.played.append((data, samplerate, device))

        module.play = play  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "sounddevice", module)
        return self


def install_fake_soundfile(
    monkeypatch: pytest.MonkeyPatch, data: Any, rate: int
) -> types.ModuleType:
    """``soundfile.read`` returns ``(data, rate)`` for any path."""
    module = types.ModuleType("soundfile")
    module.read = lambda path, dtype="float32", always_2d=False: (data, rate)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "soundfile", module)
    return module


# --- ML stack: torch, torchaudio, insightface, speechbrain, silero_vad, resemblyzer ----------


class FakeTensor:
    """Just enough of ``torch.Tensor`` for the plugins: wraps a numpy array."""

    def __init__(self, array: Any) -> None:
        import numpy as np

        self.array = np.asarray(array, dtype=np.float32)

    def unsqueeze(self, dim: int) -> FakeTensor:
        import numpy as np

        return FakeTensor(np.expand_dims(self.array, dim))

    def squeeze(self) -> FakeTensor:
        return FakeTensor(self.array.squeeze())

    def cpu(self) -> FakeTensor:
        return self

    def numpy(self) -> Any:
        return self.array

    def item(self) -> float:
        return float(self.array.reshape(-1)[0])

    def __len__(self) -> int:
        return len(self.array)

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(self.array.shape)


class FakeML:
    """Installs fake ML modules and records what the plugins ask of them."""

    def __init__(
        self, *, faces: list[tuple[Any, ...]] | None = None, missing: tuple[str, ...] = ()
    ) -> None:
        self.faces = faces if faces is not None else []
        """(score, embedding) or (score, embedding, {"bbox": ..., "kps": ...}) per face."""
        self.missing = missing
        self.events: list[tuple[Any, ...]] = []
        self.threads: list[int] = []
        self.resets = 0
        self.downloaded: set[str] = set()
        """Hugging Face models already in the local cache."""

    def install(self, monkeypatch: pytest.MonkeyPatch) -> FakeML:
        import numpy as np

        world = self

        class _Ctx:
            def __enter__(self) -> None:
                return None

            def __exit__(self, *exc: Any) -> None:
                return None

        torch = types.ModuleType("torch")
        torch.from_numpy = FakeTensor  # type: ignore[attr-defined]
        torch.set_num_threads = world.threads.append  # type: ignore[attr-defined]
        torch.inference_mode = _Ctx  # type: ignore[attr-defined]

        torchaudio = types.ModuleType("torchaudio")
        functional = types.ModuleType("torchaudio.functional")

        def resample(wav: FakeTensor, orig: int, new: int) -> FakeTensor:
            world.events.append(("resample", orig, new))
            n = int(len(wav.array) * new / orig)
            return FakeTensor(
                np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(wav.array)), wav.array)
            )

        functional.resample = resample  # type: ignore[attr-defined]
        torchaudio.functional = functional  # type: ignore[attr-defined]

        class Face(dict):  # insightface's Face is a dict with attribute access
            def __getattr__(self, name: str) -> Any:
                return self.get(name)

        class FaceAnalysis:
            def __init__(self, **kwargs: Any) -> None:
                world.events.append(("FaceAnalysis", kwargs))

            def prepare(self, **kwargs: Any) -> None:
                world.events.append(("prepare", kwargs))

            def get(self, image: Any) -> list[Face]:
                world.events.append(("get", image.shape))
                return [
                    Face(
                        det_score=score,
                        normed_embedding=np.asarray(vector, dtype=np.float32),
                        **(geometry[0] if geometry else {}),
                    )
                    for score, vector, *geometry in world.faces
                ]

        insightface = types.ModuleType("insightface")
        insightface_app = types.ModuleType("insightface.app")
        insightface_app.FaceAnalysis = FaceAnalysis  # type: ignore[attr-defined]
        insightface.app = insightface_app  # type: ignore[attr-defined]

        class EncoderClassifier:
            @classmethod
            def from_hparams(cls, **kwargs: Any) -> EncoderClassifier:
                world.events.append(("from_hparams", kwargs))
                return cls()

            def encode_batch(self, wav: FakeTensor) -> FakeTensor:
                world.events.append(("encode_batch", wav.shape))
                seed = int(abs(float(wav.array.mean())) * 1000) % 7
                return FakeTensor(np.random.default_rng(seed).standard_normal((1, 1, 192)))

        speechbrain = types.ModuleType("speechbrain")
        sb_inference = types.ModuleType("speechbrain.inference")
        sb_speaker = types.ModuleType("speechbrain.inference.speaker")
        sb_speaker.EncoderClassifier = EncoderClassifier  # type: ignore[attr-defined]

        class SileroModel:
            def __call__(self, piece: FakeTensor, rate: int) -> FakeTensor:
                window = 512 if rate == 16000 else 256
                if len(piece) != window:
                    raise ValueError(f"Provided number of samples is {len(piece)}")
                rms = float(np.sqrt(np.mean(np.square(piece.array))))
                return FakeTensor([[min(1.0, rms * 5)]])

            def reset_states(self) -> None:
                world.resets += 1

        def load_silero_vad(onnx: bool = False) -> SileroModel:
            world.events.append(("load_silero_vad", onnx))
            return SileroModel()

        silero_vad = types.ModuleType("silero_vad")
        silero_vad.load_silero_vad = load_silero_vad  # type: ignore[attr-defined]

        class VoiceEncoder:
            def __init__(self, device: str = "cpu", verbose: bool = True) -> None:
                world.events.append(("VoiceEncoder", device))

            def embed_utterance(self, wav: Any) -> Any:
                world.events.append(("embed_utterance", len(wav)))
                return np.random.default_rng(len(wav) % 5).standard_normal(256)

        def preprocess_wav(samples: Any, source_sr: int) -> Any:
            world.events.append(("preprocess_wav", source_sr))
            return np.asarray(samples)[: len(samples) // 2]  # "trimmed"

        class Piece:
            def __init__(self, text: str) -> None:
                self.text = text

        class WhisperModel:
            def __init__(self, size: str, **kwargs: Any) -> None:
                world.events.append(("WhisperModel", {"size": size, **kwargs}))

            def transcribe(self, audio: Any, **kwargs: Any) -> tuple[Any, Any]:
                world.events.append(("transcribe", audio.dtype, len(audio), kwargs))
                return iter([Piece(" doctor at"), Piece(" two ")]), None

        faster_whisper = types.ModuleType("faster_whisper")
        faster_whisper.WhisperModel = WhisperModel  # type: ignore[attr-defined]

        def pretrained(kind: str, make: Any) -> Any:
            def from_pretrained(name: str, *, cache_dir: str, local_files_only: bool) -> Any:
                world.events.append((kind, name, cache_dir, local_files_only))
                if local_files_only and name not in world.downloaded:
                    raise OSError(f"{name} is not in the cache")
                world.downloaded.add(name)
                return make()

            return types.SimpleNamespace(from_pretrained=from_pretrained)

        def tokenizer(premises: list[str], hypotheses: list[str], **kwargs: Any) -> Any:
            return {"premises": premises, "hypotheses": hypotheses}

        class NliModel:
            """Entails a hypothesis when the premise shares a word with its topic."""

            config = types.SimpleNamespace(label2id={"entailment": 0, "not_entailment": 1})

            def eval(self) -> None:
                return None

            def __call__(self, premises: list[str], hypotheses: list[str]) -> Any:
                world.events.append(("infer", len(hypotheses)))
                generic = {"this", "reminder", "about"}
                logits = []
                for premise, hypothesis in zip(premises, hypotheses, strict=True):
                    topic = set(re.findall(r"[a-z]{4,}", hypothesis.lower())) - generic
                    about = bool(topic & set(re.findall(r"[a-z]+", premise.lower())))
                    logits.append([3.0, -3.0] if about else [-3.0, 3.0])
                return types.SimpleNamespace(logits=FakeTensor(logits))

        transformers = types.ModuleType("transformers")
        transformers.AutoTokenizer = pretrained("tokenizer", lambda: tokenizer)  # type: ignore[attr-defined]
        transformers.AutoModelForSequenceClassification = pretrained("model", NliModel)  # type: ignore[attr-defined]

        resemblyzer = types.ModuleType("resemblyzer")
        resemblyzer.VoiceEncoder = VoiceEncoder  # type: ignore[attr-defined]
        resemblyzer.preprocess_wav = preprocess_wav  # type: ignore[attr-defined]

        modules = {
            "torch": torch,
            "torchaudio": torchaudio,
            "torchaudio.functional": functional,
            "onnxruntime": types.ModuleType("onnxruntime"),
            "cv2": types.ModuleType("cv2"),
            "insightface": insightface,
            "insightface.app": insightface_app,
            "speechbrain": speechbrain,
            "speechbrain.inference": sb_inference,
            "speechbrain.inference.speaker": sb_speaker,
            "silero_vad": silero_vad,
            "resemblyzer": resemblyzer,
            "faster_whisper": faster_whisper,
            "transformers": transformers,
        }
        for name, module in modules.items():
            module.__spec__ = importlib.machinery.ModuleSpec(name, None)
            blocked = name in self.missing or name.split(".")[0] in self.missing
            monkeypatch.setitem(sys.modules, name, None if blocked else module)
        return self

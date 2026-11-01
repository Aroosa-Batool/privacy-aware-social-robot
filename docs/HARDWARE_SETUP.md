# Hardware setup

`uv sync` installs everything the robot needs: `ohbot` and `pyserial` (head and lip-synced
speech), `bleak` (watch), `sounddevice` and `soundfile` (microphone, speaker output, WAV files),
`opencv-python`, `insightface` and `onnxruntime` (camera, face model), and `torch`, `torchaudio`,
`speechbrain`, `silero-vad` and `faster-whisper` (voice model, voice activity, speech-to-text), and
`transformers` (sensitivity model).
The lighter Resemblyzer voice model is optional: `uv sync --extra resemblyzer` (it builds
`webrtcvad` from source).

```bash
uv sync
uv run pasr hardware list      # what is plugged in: serial ports, microphones, speakers, cameras, watches
uv run pasr hardware check     # exercise each device once
```

The dashboard's **Setup** page does the same, and also downloads the models with progress.
Scanning and testing need the robot stopped: they hold the same lock as a running robot, so they
never fight over the devices.

## Ohbot (`hardware.ohbot`)

- USB serial. On this Mac it appears as `/dev/cu.usbmodem101` (use `cu.*`, not `tty.*`).
  `port: auto` lets the library probe every `*usb*` serial port; set the port explicitly if
  other USB serial devices are attached.
- Library `ohbot` 4.0.18. Its install requirements list `comtypes` (Windows-only); `uv sync`
  resolves it on macOS.
- **The import has side effects**: `import ohbot` creates `ohbotData/` in the current working
  directory, copies the motor definitions there and connects to the robot. The adapter therefore
  imports it only inside `OhbotDriver.ensure_started`, after switching the process to
  `<project>/.ohbot/` (git-ignored). Nothing of this lands in `data/`.
- The library is **not thread-safe** (no locks; `say()` starts a lip-sync thread that calls
  `move()`). `OhbotDriver` is the single owner: one lock around every call, shared by `OhbotHead`
  and `OhbotSpeaker`. The speaker starts the driver itself, so it can speak before the head has
  connected.
- Motors: HEADNOD 0, HEADTURN 1, EYETURN 2, LIDBLINK 3, TOPLIP 4, BOTTOMLIP 5, EYETILT 6; positions
  0–10. Left/front/right for the camera scan are `hardware.ohbot.turn_left/turn_front/turn_right`
  (defaults 2/5/8, Advanced tier). Calibrate them on the real head with
  `pasr hardware check --device ohbot` and watch where the camera points.
- `look()` returns after a time estimate (`hardware.ohbot.move_seconds`, scaled by distance and
  speed); the scan then waits `scan.settle_seconds` before grabbing frames.
- **Following faces** (`scan.follow`, Settings › Hardware › Follow faces; off by default):
  `nudge()` turns HEADTURN and nods HEADNOD by small steps, within 0–10. To tune it on the real
  head, switch on the live view (Home), stand at the edge of the camera's view and run a
  sensitive test reminder. If the head turns or nods *away* from you, switch on
  `invert_turn` / `invert_nod`. If it overshoots, lower `turn_gain` / `nod_gain`; if it needs
  many small steps, raise them. The gain is the motor units for a face at the edge of the image,
  so about half the camera's field of view in motor units.
- Speech: `ohbot.say(text, lipSync=True)` runs macOS `say -o` into `.ohbot/ohbotData/ohbotspeech.wav`,
  plays it, and returns on an estimate of the end. The driver deletes that file after every
  utterance (it contains the reminder title) and strips shell metacharacters from the text,
  because the library builds a shell command string. `hardware.speaker.backend: macos_say`
  speaks through `say` directly (argv, no file, no lip sync); `hardware.speaker.voice` picks the
  voice.

- **Where the voice comes out:** the Ohbot has no speaker of its own. Set
  `hardware.speaker.output_device` (e.g. `MacBook Air Speakers`; names from `pasr hardware list`)
  so the voice does not follow the macOS default output , otherwise AirPods or a display that
  became the default get the voice and the robot moves its lips silently. With the `ohbot`
  backend the library still generates the speech and drives the lips, and `sounddevice` plays
  the file on that device; with `macos_say` it is passed to `say -a`.

## Bangle.js 1 watch (`hardware.watch`)

- Load the consent app (`bangle/consent_app.js`) as described in [bangle/README.md](../bangle/README.md).
- `BleakTransport` finds the watch by name prefix (`name_prefix: Bangle.js`) and caches its
  address in `data/settings.json` (`hardware.watch.address`). macOS identifies devices by a
  CoreBluetooth UUID, not a MAC address, so the cached value only works on the machine that
  found it. The next start tries the cached address first and falls back to a scan.
- The watch drops the link when it sleeps. The transport notices (disconnected callback) and
  `BangleWatch` reconnects before each request; `reconnect_attempts` and
  `scan_timeout_seconds` bound how long that takes.
- Bluetooth off, or a terminal without Bluetooth permission, is reported as
  "Bluetooth is off, or this terminal has no Bluetooth permission".
- `pasr hardware check --device watch` (or the Setup page) connects and asks whether the app
  is loaded; "consent is not defined" means it is not , send it again from the Espruino IDE.
- Protocol: [WATCH_PROTOCOL.md](WATCH_PROTOCOL.md).

## Head camera (`hardware.camera`)

- USB webcam on the head, so turning the head moves the camera. `index` is the OpenCV index;
  `pasr hardware list` opens indices 0–3 to show which exist. An iPhone with Continuity Camera
  often takes index 0 and shifts the others.
- OpenCV with the AVFoundation backend on macOS. The device is opened only in `open()` and
  released in `close()`, so the camera LED is dark unless the robot is enrolling or scanning.
  `warmup_frames` are discarded after opening while the exposure settles.
- The camera runs in a helper process (ADR 0010). If it sends no frame for 3 s, the robot
  reconnects it for up to 10 s, and the dashboard says so in a toast. **If the camera drops off
  USB when the head turns** (the toast says "sent no frame … reconnecting it", or the macOS log
  shows `HD Webcam C615 … hardware connection lost`), give its cable slack and strain relief at
  the head, and try a port on the Mac itself instead of the dock.
- Frames are HxWx3 uint8 in **BGR** order (OpenCV's convention; InsightFace expects BGR).
- `source: images` with `image_dir` replaces the device by a researcher-supplied folder of
  images (jpg/jpeg/png/bmp, read in name order, cycling). Read-only; nothing is ever written.

## Microphone (`hardware.microphone`)

- Laptop microphone through `sounddevice`. `device` is a name from `pasr hardware list` (empty =
  system default). Choose one explicitly if AirPods or a display microphone keep taking over.
- Audio is mono float32 at `sample_rate` (16 kHz) in chunks of `chunk_ms` (32 ms = 512 samples,
  the window Silero VAD needs). The PortAudio callback hands chunks to the event loop; overflows
  are counted and logged, never written anywhere.
- `source: wav` with `wav_path` replaces the device by a researcher-supplied WAV file (mono or
  stereo, **at `sample_rate`** , resample first with `ffmpeg -i in.wav -ar 16000 -ac 1 out.wav`).
  The stream ends with the file. `wav_realtime: true` paces chunks like a room;
  `false` (or `pasr calibrate --fast`) delivers them as fast as possible.

## Models (`perception.*`, `storage.models_dir`)

```bash
uv run pasr models status          # installed? weights downloaded?
uv run pasr models download        # load the configured models once (face, voice, speech, sensitivity)
```

Weights go to `models/` (git-ignored, never inside `data/`). InsightFace downloads `buffalo_l`
on first use; SpeechBrain fetches `spkrec-ecapa-voxceleb`, faster-whisper its `base` model and
the sensitivity plugin `deberta-v3-base-zeroshot-v2.0` from the Hugging Face hub; Silero and
Resemblyzer ship inside their packages. After that everything runs offline. Install them from
the Setup page (tick the models you want) or with `pasr models download`. Then calibrate
(`pasr calibrate`).

## macOS permissions

Camera, microphone and Bluetooth permission prompts belong to the app that launches Python
(Terminal, iTerm or VS Code). Run `pasr hardware check` from a normal terminal the first time
and allow each prompt. Over SSH no prompt appears and the devices silently fail.

## Hardware and model tests

The default test run uses stand-in devices and needs no robot. These two markers are excluded
from it (`pyproject.toml`) and run the real thing:

```bash
PASR_HW_TESTS=1 uv run pytest -m hardware          # robot connected: head, speech, watch ping
PASR_TEST_WAV_OWNER=owner.wav PASR_TEST_WAV_OTHER=friend.wav \
PASR_TEST_IMAGES_OWNER=~/exp/owner PASR_TEST_IMAGES_OTHER=~/exp/friend \
  uv run pytest -m models                           # real plugins over your own recordings
```

The media files stay on your disk; the repository never contains any (see `.gitignore`).

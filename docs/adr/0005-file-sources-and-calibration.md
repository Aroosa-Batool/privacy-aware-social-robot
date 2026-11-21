# 0005 , File-backed research sources and threshold calibration

**Status:** accepted (M2)

**Context.** Experiments must be repeatable and the models must be checked against real
recordings, but ADR 0002 forbids the robot from storing media. Thresholds are model-specific:
a threshold that suits one model means nothing for another model's embeddings.

**Decisions.**
- A researcher-supplied **WAV file** can stand in for the microphone and an **image folder**
  for the camera (`hardware.microphone.source: wav`, `hardware.camera.source: images`). They are
  selected by a `source` field on the device's settings and behave exactly like the devices
  they replace (they carry no hidden information about who is in them). They only read; the
  lint rules and tests that stop the robot writing media are unchanged.
- The WAV source requires the configured sample rate (no resampling dependency; bit-exact and
  reproducible , resample once with ffmpeg), ends with the file instead of looping (looping would
  double-count speakers in calibration and hide a too-short recording), and paces chunks on the
  robot's clock by default so `pasr run` behaves like a room.
- **Calibration** scores fresh samples of the owner and of other people against the enrolled
  owner exactly as `identity.identify` does at runtime (`domain/calibration.py`), suggests the
  threshold that balances false accepts and false rejects (or, when no other person was
  captured, a margin below the owner's scores but never above the plugin's recommended
  threshold, since the owner's scores alone cannot show how high it may go), and stores **only
  that number**
  (`identity.face_threshold` / `voice_threshold`). Other people's embeddings never leave the
  capture step. Each plugin declares a `recommended_threshold` as a starting point. (The
  warning shown when the configured threshold was far from it was removed on 2026-11-01.)

**Consequences.**
- `pasr calibrate` and the Calibration page work live or from files; `pytest -m models` runs
  the real plugins over the researcher's own recordings via environment variables.
- Changing the face or speaker plugin means re-enrolling *and* re-calibrating.

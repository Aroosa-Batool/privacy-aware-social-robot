# 0006 , The product is real-only; stand-ins live in the tests

**Status:** accepted (M3)

**Context.** M0 built the robot first as a simulation: fake devices, fake perception plugins, a
scripted room, YAML scenarios on a virtual clock, a `hardware.mode` fake/real switch and a
dashboard Simulation page. With the robot, the watch and the models working (M1, M2), the owner
wanted the repository to contain only what runs on the real robot.

**Decision.** `src/pasr` contains only real implementations: no fake devices or plugins, no
simulated room, no hardware mode, no `sim_*` fields on frames and audio, no scenario runner.
Everything the robot needs is a core dependency, so a plain `uv sync` installs it (and `uv run`,
which syncs the environment exactly, never removes it). The default models are the real ones
(InsightFace, SpeechBrain ECAPA, Silero VAD, faster-whisper), with thresholds matching them.

Tests still have to exercise the reminder flow, consent memory and privacy guarantees without the
robot. They use stand-ins under `tests/support/`: a scripted room, devices acting on it,
perception plugins registered as `stand_in`, a virtual clock, and the scenario runner (scenario
files in `tests/scenarios/data/`). The product offers only two generic seams for this:
`Runtime(hardware=...)` and `Runtime(inline_compute=True)`.

**Consequences.**
- `pasr run --simulate`, `pasr scenarios` and the dashboard's Simulation page are gone; the
  dashboard's *Quick test* reminder runs the pipeline on the robot instead.
- Repeatable experiments use recorded WAV files and image folders (ADR 0005).
- CI installs the full dependency set (CPU-only torch on Linux) and runs the stand-in tests;
  `pytest -m hardware` and `-m models` run against the robot and the real models.

---
title: Development and tests
nav: Development
description: Lint, types and tests in one line. The default test run needs no robot; the hardware and model tests run against the real thing.
---

## The checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run pre-commit install            # run the same checks on every commit
```

The pre-commit hooks also strip trailing whitespace, check YAML, refuse private keys and merge
markers, reject files over **500 KB** (recordings, images and models stay out of git), and run
`node --check` on the watch app. CI (GitHub Actions) runs the checks on Ubuntu and macOS.

## Repository layout

```text
src/pasr/        Python package: domain, settings, perception, hardware, storage, live,
                 orchestration, apps/reminder, dashboard, cli
config/          default.yaml (generated reference), profiles/
bangle/          Bangle.js watch app (Espruino JavaScript)
docs/            architecture, privacy, protocol, hardware, decision records (adr/)
website/         this documentation site
tests/           unit/, component/, scenarios/, dashboard/ (stand-in devices in support/),
                 hardware/ (-m hardware, the robot), models/ (-m models, the real models)
data/            runtime data: database, local settings (git-ignored)
models/          downloaded model weights (git-ignored)
.ohbot/          working directory of the ohbot library (git-ignored)
```

## Test without the robot

The product contains only real implementations ([ADR 0006](/decisions/0006-real-only-product)).
The tests swap in stand-ins from `tests/support/`: a **scripted room** (who is there, who speaks,
where they stand), **devices** that act on it, **perception plugins** registered as `stand_in`,
and a **virtual clock**. The product offers two seams for this: `Runtime(hardware=...)` and
`Runtime(inline_compute=True)`. A 7-minute reminder flow runs in milliseconds.

| Folder | What it tests |
|---|---|
| `tests/unit/` | Pure logic, adapters with fakes, the watch protocol, the watch app under Node, settings, storage. |
| `tests/component/` | The runtime, enrolment, calibration, the Bangle watch against an emulation, face following, live view. |
| `tests/scenarios/` | Whole reminder flows from YAML files, on stand-in devices. |
| `tests/dashboard/` | Every dashboard page renders (Streamlit's testing API). |
| `tests/hardware/` | The real robot (`-m hardware`). |
| `tests/models/` | The real models on your recordings (`-m models`). |

## Scenario tests

Each YAML file in `tests/scenarios/data/` scripts a room and a reminder, and states the expected
path through the state machine and what may be stored. Examples:

| Scenario | Checks |
|---|---|
| `sensitive_owner_alone` | Only the owner: the reminder is spoken. |
| `audio_bystander_consent_yes` / `_no` | A stranger speaks; the owner answers Yes or No. |
| `silent_bystander_seen_by_camera` | Nobody else speaks, but the scan sees someone. |
| `ask_once_remembers_bystander` | The second time, the robot does not ask. |
| `consent_timeout_goes_to_watch` | No answer counts as No. |
| `owner_away_never_senses` | The watch does not answer: no sensor opens, nothing is said. |
| `owner_leaves_before_due` | The watch stops answering before the due time. |
| `audio_only_never_uses_camera` · `camera_only_never_listens` | The detection choice is respected. |
| `no_detection_always_asks` · `always_disclose` · `non_sensitive_spoken` | The policy table. |
| `owner_voice_still_scans` · `owner_voice_no_scan` | `scan_if_only_owner_heard` on and off. |

After every scenario the suite checks that the database holds only float32 vectors of the declared
size as binary data and that the data folder holds nothing but the database. All scenarios also
run with face following on. Add a scenario by adding a YAML file.

## With the robot and the models

```bash
PASR_HW_TESTS=1 uv run pytest -m hardware          # head, speech, watch ping
PASR_TEST_WAV_OWNER=owner.wav PASR_TEST_WAV_OTHER=friend.wav \
PASR_TEST_IMAGES_OWNER=~/exp/owner PASR_TEST_IMAGES_OTHER=~/exp/friend \
  uv run pytest -m models                           # real plugins on your recordings
```

## This documentation

The site is built from `website/` by a small Python script and deployed to GitHub Pages by
`.github/workflows/docs.yml` on every push to `main` that touches it.

```bash
uv run website/build.py --serve      # http://localhost:8000
```

Pages are Markdown files in `website/pages/`; `website/nav.yml` orders them; decision records come
straight from `docs/adr/`. See `website/README.md`.

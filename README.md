# privacy-aware-social-robot

A personal social robot that keeps its owner's private information private. An
[Ohbot](https://www.ohbot.co.uk) robot head with a head-mounted camera reminds its owner of
appointments. Before saying a **sensitive** reminder ("your doctor's appointment is at 2 pm") out
loud, it checks whether anyone else is in the room , first by listening, then by looking around ,
and asks the owner on a **Bangle.js** watch whether to go ahead. The robot stores **no audio or
video**, only face and voice embeddings.

The repository is also a research platform. A dashboard shows the pipeline live and lets
researchers swap and tune the algorithm of each stage, grouped as voice, face and
sensitivity.
Recorded WAV files and image folders can stand in for the microphone and camera, so an
experiment can be repeated on the same input.

> **Status: milestones M0–M3.** Everything runs on the real robot: Ohbot head and lip-synced
> speech, Bluetooth watch, head camera and microphone, local models (InsightFace, SpeechBrain
> ECAPA, Silero VAD, faster-whisper, a zero-shot sensitivity model), real enrolment, threshold
> calibration and voice reminders , see the [roadmap](#roadmap).

**Documentation:** <https://aroosa-batool.github.io/privacy-aware-social-robot/> , a dashboard
tour with recordings, hardware setup, the privacy model, every command and setting, and the
design decisions.

PASR is the software of Aroosa Batool's Master's thesis in Computer Science at the University of
Siegen, *From Consent to Privacy Management: Investigating Users' Perceptions of a Social Robot
That Remembers Their Privacy Preferences for Sensitive Information Disclosure*, written in the
Ubiquitous Computing group (Department of Electrical Engineering and Computer Science) and
supervised by Univ.-Prof. Dr. Kristof Van Laerhoven and Atikkhan Nilgar.

## Quick start

Requires macOS (Apple Silicon tested), [uv](https://docs.astral.sh/uv/), the robot, the watch
and (for the watch app) Node.js. Setup details: [docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md).

```bash
uv sync                              # Python 3.12 with everything the robot needs
uv run pasr hardware list            # serial ports, microphones, speakers, cameras, watches
uv run pasr config set hardware.speaker.output_device "MacBook Air Speakers"
uv run pasr hardware check           # move the head, speak, grab a frame, listen, ping the watch
uv run pasr models download          # one-time weight download (the only network access)
uv run pasr setup                    # register the owner, enrol face and voice, two questions
uv run pasr calibrate voice --others 1 --apply   # measure the owner against another person
uv run pasr reminder add "doctor's appointment at 2pm"   # asks: on what date?
uv run pasr run                      # or: uv run pasr dashboard  (http://localhost:8501)
```

Or do it all in the dashboard (`uv run pasr dashboard`):

1. **Settings › Setup** , scan what is connected, test each device, and tick and install the
   models (once, before enrolling). Set the Ohbot port, speaker output device or microphone
   with `uv run pasr config set` (as above).
2. **Settings › Models** , choose the model for each stage of the experiment.
3. **Start robot** (top right), then **Profile** , capture face and voice, make the
   privacy choices (whether to remember your watch answers for each person is one of them).
   Calibrate the thresholds from the terminal (`uv run pasr calibrate`, as above).
4. **Home › Reminders** , type one, add a **Quick test** to watch the whole pipeline, or set one
   **by voice**; **Home** shows the pipeline live.

> **Clone inside iCloud Drive (e.g. `~/Documents`)?** iCloud marks files inside `.venv` as hidden,
> and Python 3.12 then ignores the project's editable install (`No module named 'pasr'`). Keep the
> virtual environment outside iCloud, for example
> `export UV_PROJECT_ENVIRONMENT=~/.venvs/privacy-aware-social-robot` in your shell profile.

## How it works

1. **Profile** , the owner registers. The robot captures face and voice **embeddings** and asks:
   - *Detection*: microphone only · camera only · microphone and camera · nothing
   - *Behaviour*: always say reminders · always ask on the watch · ask once per person and remember
2. **Reminders** , typed (dashboard, `pasr reminder add`) or spoken. Missing time → 00:00
   (configurable). Missing date → the robot asks for one. A classifier marks reminders as
   sensitive (e.g. *doctor*) or not (e.g. *groceries*).
3. **Owner presence first** , when any reminder's flow starts, the robot first pings the
   owner's watch over Bluetooth. No answer → the owner is away: no microphone, no camera,
   nothing said out loud; the reminder goes to the watch. It checks again right before speaking.
4. **When a sensitive reminder is due** , the robot wakes up 7 minutes early and listens for 5
   minutes. A voice that is not the owner's means a bystander. If it hears no stranger and the
   camera is allowed, it looks left, front and right for silent bystanders. If someone is there,
   it asks on the watch. *Yes* → it says the reminder at the due time. *No* or no answer → the
   reminder goes to the watch instead. Any error → the watch (fail closed).
5. **Consent memory** , with the ask-once policy, answers are remembered per bystander (as an
   anonymous embedding and label). *Delete last consent* and a two-level **reset** are available.

**Live view** , watch face and voice recognition as it happens. Whenever the robot listens,
scans, enrols or calibrates, a window opens on the laptop with each analysed camera frame,
every face boxed and labelled (owner or someone else, with its similarity to the owner), the
microphone level, and what each speech segment matched; close it with q or Esc. Switch it on
with **Live view window** in the dashboard's top bar, `--live-view` on `pasr run`,
`pasr setup` or `pasr calibrate`, or `uv run pasr config set live_view.enabled true`. It is off
by default: nothing is stored, but people nearby appear on screen.

Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/PRIVACY.md](docs/PRIVACY.md) ·
[docs/WATCH_PROTOCOL.md](docs/WATCH_PROTOCOL.md) · [docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md) ·
[decisions](docs/adr/)

## Commands

| Command | What it does |
|---|---|
| `pasr setup [--no-face] [--no-voice] [--live-view]` | Owner, face and voice enrolment, the two privacy questions |
| `pasr calibrate face\|voice [--others N] [--apply] [--wav F…] [--images DIR…] [--fast] [--live-view]` | Measure owner-vs-others similarity, suggest and save a threshold |
| `pasr hardware list` · `check [--device D]` | Discover and test the devices (also the dashboard's Setup page) |
| `pasr models status` · `download [--kind K]` | Local model weights |
| `pasr run [--profile FILE] [--live-view]` | Run the robot until Ctrl+C |
| `pasr dashboard` | Open the researcher dashboard |
| `pasr reminder add TEXT [--date D] [--sensitive/--not-sensitive]` · `list` · `delete ID` | Reminders |
| `pasr consent list` · `delete-last [--hard]` | Remembered consent |
| `pasr reset [--delete-owner/--keep-owner] [--purge-log]` | Reset the app |
| `pasr config show --level basic\|advanced` · `set KEY VALUE` · `diff` · `dump` · `reset` | Settings |

Settings layer from lowest to highest priority: built-in defaults ([config/default.yaml](config/default.yaml)),
an optional `--profile` YAML, saved changes (`data/settings.json`), `.env` / `PASR__GROUP__FIELD`
environment variables ([.env.example](.env.example)), and command-line flags.

## Repository layout

```
src/pasr/        Python package (domain, settings, perception, hardware, storage, live,
                 orchestration, apps/reminder, dashboard, cli)
config/          default.yaml (generated reference), profiles/
bangle/          Bangle.js 1 watch app (Espruino JavaScript)
docs/            architecture, privacy, protocol, hardware, decision records
website/         documentation site, published to GitHub Pages (website/README.md)
tests/           unit/, component/, scenarios/, dashboard/ (on stand-in devices in support/),
                 hardware/ (-m hardware, the robot), models/ (-m models, the real models)
data/            runtime data (database, local settings) , git-ignored
models/          downloaded model weights , git-ignored
.ohbot/          working directory of the ohbot library , git-ignored
```

## Development

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run pre-commit install            # run the same checks on every commit
```

The default test run needs no robot: tests drive the reminder flow with stand-in devices and
perception from `tests/support/` on a virtual clock. With the robot connected, run
`PASR_HW_TESTS=1 uv run pytest -m hardware`. CI (GitHub Actions) runs the checks on Ubuntu and
macOS, plus `node --check` on the watch app.

## Roadmap

| Milestone | Scope |
|---|---|
| **M0** ✅ | Structure, interfaces, state machine, storage, settings, CLI, dashboard, watch app source, tests, CI |
| **M1** ✅ | Real Ohbot head and speech; Bluetooth watch transport; watch app on the device |
| **M2** ✅ | Real camera and microphone; InsightFace, Resemblyzer / ECAPA, Silero VAD; real enrolment; threshold calibration; WAV / image-folder research sources |
| **M3** ✅ | Local speech-to-text (faster-whisper) for voice reminders |
| **M4** | Experiment tooling and metrics; researcher handbook; optional Google Calendar import |

**Deliberately not built (yet):** cloud deployment or battery operation, multiple owners or
logins, a mobile app, any cloud or LLM service (everything runs locally), model training, raw
media storage or live video in the dashboard.

## License

MIT , see [LICENSE](LICENSE). Downloaded model weights have their own licences
(see [docs/PRIVACY.md](docs/PRIVACY.md#models-and-licences)).

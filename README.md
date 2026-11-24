# privacy-aware-social-robot

A personal social robot that reminds its owner of appointments without giving their private
information away to whoever else is in the room.

The robot is an [Ohbot](https://www.ohbot.co.uk) head with a camera mounted on it. Saying a
reminder like "buy groceries" out loud is harmless, but "your doctor's appointment is at 2 pm"
is not something the owner necessarily wants a visitor to hear. So before the robot says a
**sensitive** reminder, it first checks whether anyone else is around: it listens for voices that
are not the owner's, and then turns its head to look around the room. If it finds someone, it asks
the owner on a **Bangle.js** watch whether it may go ahead. A robot that protects privacy should
not create a new privacy risk itself, so it stores **no audio or video**, only face and voice
embeddings (numeric fingerprints that cannot be played back or viewed).

The repository is also a research platform. A dashboard shows each step of the pipeline as it
runs, and lets a researcher swap and tune the algorithm used at each stage (grouped as voice,
face and sensitivity). Recorded WAV files and image folders can stand in for the microphone and
camera, so an experiment can be repeated on exactly the same input.

> **Status: milestones M0–M3 are done.** Everything runs on the real robot: the Ohbot head with
> lip-synced speech, the Bluetooth watch, the head camera and microphone, local models
> (InsightFace, SpeechBrain ECAPA, Silero VAD, faster-whisper and a zero-shot sensitivity model),
> real enrolment, threshold calibration and reminders set by voice. See the [roadmap](#roadmap)
> for what comes next.

**Documentation:** <https://aroosa-batool.github.io/privacy-aware-social-robot/>. The site has a
dashboard tour with screen recordings, the hardware setup, the privacy model, every command and
setting, and the reasoning behind each design decision.

PASR is the software of Aroosa Batool's Master's thesis in Computer Science at the University of
Siegen, *From Consent to Privacy Management: Investigating Users' Perceptions of a Social Robot
That Remembers Their Privacy Preferences for Sensitive Information Disclosure*, written in the
Ubiquitous Computing group (Department of Electrical Engineering and Computer Science) and
supervised by Univ.-Prof. Dr. Kristof Van Laerhoven and Atikkhan Nilgar.

## Quick start

You need macOS (tested on Apple Silicon), [uv](https://docs.astral.sh/uv/), the robot, the watch
and, to install the watch app, Node.js. The full hardware walkthrough is in
[docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md).

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

The order matters: the models must be downloaded before you enrol, because enrolment turns your
face and voice into embeddings with those models. Calibration then measures how far your own
scores sit from someone else's, so the robot can tell the two of you apart reliably.

You can also do all of this in the dashboard (`uv run pasr dashboard`):

1. **Settings › Setup.** Scan for connected devices, test each one, then tick and install the
   models (once, before enrolling). The Ohbot port, speaker output device and microphone are set
   with `uv run pasr config set`, as above.
2. **Settings › Models.** Choose which model runs at each stage of the experiment.
3. **Start robot** (top right), then **Profile.** Capture your face and voice and make the
   privacy choices, including whether the robot should remember your watch answers for each
   person. Then calibrate the thresholds on **Settings › Calibration** (or with
   `uv run pasr calibrate`).
4. **Home › Reminders.** Type a reminder, add a **Quick test** to watch the whole pipeline run
   within a few minutes, or set one **by voice**. **Home** shows the pipeline live.

> **Cloned inside iCloud Drive (for example `~/Documents`)?** iCloud marks files inside `.venv` as
> hidden, and Python 3.12 then ignores the project's editable install, so you get
> `No module named 'pasr'`. Keep the virtual environment outside iCloud, for example by adding
> `export UV_PROJECT_ENVIRONMENT=~/.venvs/privacy-aware-social-robot` to your shell profile.

## How it works

1. **Profile.** The owner registers once. The robot captures face and voice **embeddings** and
   asks two questions that decide how it behaves from then on:
   - *Detection:* how may it check for other people? Microphone only, camera only, microphone and
     camera, or not at all.
   - *Behaviour:* what should it do with a sensitive reminder when someone may hear it? Always say
     it, always ask on the watch, or ask once per person and remember the answer.
2. **Reminders.** A reminder can be typed (on the dashboard or with `pasr reminder add`) or
   spoken. A typed reminder without a time is set for 00:00 (configurable); one without a date
   makes the robot ask for the date. A local classifier then marks each reminder as sensitive
   (for example *doctor*) or not (for example *groceries*). You can always override its decision.
3. **Owner presence first.** Whenever a reminder's flow starts, the robot first pings the owner's
   watch over Bluetooth. If the watch does not answer, the owner is treated as away. There is
   then no reason to listen or look around, so the microphone and camera stay off, nothing is said
   out loud, and the reminder goes to the watch. The robot checks again right before it speaks,
   in case the owner has left in the meantime.
4. **Checking the room for a sensitive reminder.** The robot wakes up 7 minutes before the due
   time so it has time to check, and listens for 5 minutes. A voice that is not the owner's means
   a bystander. Some people stay silent, so if it hears no stranger and the camera is allowed, it
   then sweeps the room for faces until the due time (at three head heights, looking right, front
   and left), and looks more closely at any face it cannot recognise at once. If it finds
   someone, it asks on the watch. *Yes* means it says the reminder at the due time. *No*, or no
   answer, means the reminder goes privately to the watch instead. Any error also sends it to the
   watch: when in doubt, the robot stays quiet (it *fails closed*).
5. **Consent memory.** With the ask-once policy, the robot remembers each answer per bystander,
   stored as an anonymous label and an embedding, never a name. The owner can take back the last
   answer with *Delete last consent*, and a two-level **reset** wipes the remembered data.

**Live view.** While you develop or demonstrate the robot, it helps to see what face and voice
recognition decide as they decide it. Whenever the robot listens, scans, enrols or calibrates, the
live view opens a window on the laptop showing each analysed camera frame, with every face boxed
and labelled (the owner or someone else, with its similarity to the owner), the microphone level,
and what each speech segment matched. Close it with q or Esc. Turn it on with **Live view
window** in the dashboard's top bar, with `--live-view` on `pasr run`, `pasr setup` or
`pasr calibrate`, or with `uv run pasr config set live_view.enabled true`. It is off by default:
it stores nothing, but it does show people nearby on screen.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/PRIVACY.md](docs/PRIVACY.md) ·
[docs/WATCH_PROTOCOL.md](docs/WATCH_PROTOCOL.md) · [docs/HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md) ·
[design decisions](docs/adr/)

## Commands

| Command | What it does |
|---|---|
| `pasr setup [--no-face] [--no-voice] [--live-view]` | Registers the owner, enrols face and voice, and asks the two privacy questions |
| `pasr calibrate face\|voice [--others N] [--apply] [--wav F…] [--images DIR…] [--fast] [--live-view]` | Measures how similar the owner is to other people, then suggests (and with `--apply` saves) a threshold |
| `pasr hardware list` · `check [--device D]` | Finds and tests the devices (the dashboard's Setup page does the same) |
| `pasr models status` · `download [--kind K]` | Shows or downloads the local model weights |
| `pasr run [--profile FILE] [--live-view]` | Runs the robot until you press Ctrl+C |
| `pasr dashboard` | Opens the researcher dashboard |
| `pasr reminder add TEXT [--date D] [--sensitive/--not-sensitive]` · `list` · `delete ID` | Adds, lists and deletes reminders |
| `pasr consent list` · `delete-last [--hard]` | Shows or takes back remembered consent answers |
| `pasr reset [--delete-owner/--keep-owner] [--purge-log]` | Resets the app |
| `pasr config show --level basic\|advanced` · `set KEY VALUE` · `diff` · `dump` · `reset` | Reads and changes settings |

Settings are layered, from lowest to highest priority: the built-in defaults
([config/default.yaml](config/default.yaml)), an optional `--profile` YAML, changes saved from the
dashboard or CLI (`data/settings.json`), `.env` / `PASR__GROUP__FIELD` environment variables
([.env.example](.env.example)), and finally command-line flags. A higher layer overrides a lower
one, so you can keep a study's settings in a profile and still try out a single change from the
command line.

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
data/            runtime data (database, local settings); git-ignored
models/          downloaded model weights; git-ignored
.ohbot/          working directory of the ohbot library; git-ignored
```

## Development

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run pre-commit install            # run the same checks on every commit
```

You do not need the robot to run the default tests. They drive the reminder flow with stand-in
devices and perception from `tests/support/` on a virtual clock, so they never wait out a
reminder's minutes in real time. With the robot connected, run `PASR_HW_TESTS=1 uv run pytest -m hardware`
to test the real devices. CI (GitHub Actions) runs the checks on Ubuntu and macOS, plus
`node --check` on the watch app.

## Roadmap

| Milestone | Scope |
|---|---|
| **M0** ✅ | Structure, interfaces, state machine, storage, settings, CLI, dashboard, watch app source, tests, CI |
| **M1** ✅ | Real Ohbot head and speech; Bluetooth watch transport; watch app on the device |
| **M2** ✅ | Real camera and microphone; InsightFace, Resemblyzer / ECAPA, Silero VAD; real enrolment; threshold calibration; WAV / image-folder research sources |
| **M3** ✅ | Local speech-to-text (faster-whisper) for voice reminders |
| **M4** | Experiment tooling and metrics; researcher handbook; optional Google Calendar import |

**Deliberately not built (yet):** cloud deployment or battery operation, multiple owners or
logins, a mobile app, any cloud or LLM service (everything runs locally), model training, storage
of raw media, and live video in the dashboard.

## License

MIT; see [LICENSE](LICENSE). Downloaded model weights have their own licences
(see [docs/PRIVACY.md](docs/PRIVACY.md#models-and-licences)).

# 0008 , A live view of recognition, in its own window

**Status:** accepted

**Context.** During development and demonstrations the researcher needs to see what face and
voice recognition decide while it happens: which faces were found, who each one was taken for,
how close each voice was to the owner's, and how calibration samples score. The event log only
holds labels and numbers after the fact. The robot runs either from the dashboard or from a
terminal (`pasr run`, `setup`, `calibrate`).

**Decisions.**
- A **desktop window on the laptop** shows it, whichever way the robot runs. A panel inside the
  dashboard was tried and dropped: re-rendering frames and charts through Streamlit every half
  second lagged noticeably, and captures had to move to the background to keep the page alive.
- One in-memory **feed** (`pasr.live.feed`) holds what the window shows: the latest frame, about
  three seconds of microphone levels and the last six labels, kept only inside the listening,
  scanning, enrolment and calibration steps.
- The window is a **separate process** (`pasr.live.window`) fed through a pipe: macOS opens
  windows only on a main thread, the dashboard runs the robot on a background thread, and an
  in-process window would stall the robot's event loop while it is dragged. A slow or stuck
  window never delays a reminder (the oldest messages are dropped). The window opens when a step
  starts; closed by the user, it opens again at the next step; it closes with the robot.
- It shows each analysed camera frame with its faces boxed and labelled, the microphone level
  and speech probability, a few seconds of level history, and each speech segment's match.
  Calibration samples show their similarity to the enrolled owner.
- **Off by default** (`live_view.enabled`; the Overview page's toggle; `--live-view` for one
  terminal run). The window never shows the camera outside those steps, never shows a reminder
  title, and stays shut while the owner is away. Nothing is written to disk, and the event-log
  rules are unchanged.
- Colours: blue for the owner, orange for anyone else, aqua for enrolment samples and grey for
  unused input, a set that stays distinguishable for every type of colour vision; every box and
  row also carries a text label.

**Consequences.**
- People near the robot appear on the laptop's screen while it is on, including bystanders who
  have not consented to anything. That is acceptable for development, or for study sessions
  whose participants agreed to it, and is documented in docs/PRIVACY.md.
- Face plugins may report a bounding box (`FaceObservation.box`) for the window; it is never
  stored or logged. Plugins without one still work: their labels are listed under the frame.

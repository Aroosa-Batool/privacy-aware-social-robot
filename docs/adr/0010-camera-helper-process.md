# 0010 , The camera in a helper process, and every problem as a toast

**Status:** accepted

**Context.** The head camera (a Logitech C615) sits on the moving head, behind the dock's USB
hubs. On 1 November 2026 it dropped off USB twice ("hardware connection lost" in the macOS log),
once the moment the head turned during a scan, and was back on USB 0.2 s later. The robot still
failed: in the process that had the camera open, macOS kept handing OpenCV the old, removed
device (`Invalid streamID`), for 19 minutes in one case, until the dashboard was restarted. A
new process opened the camera at once. The dashboard showed the failure only as a stage of the
pipeline, and other problems (the watch not answering, an error outside a reminder) only in the
terminal.

**Decisions.**
- The webcam is opened in a **helper process**, `python -m pasr.hardware.camera.helper`, the
  only code that opens a camera through OpenCV. It sends a frame for each request over a pipe,
  in memory, and releases the camera when the pipe closes, also when the robot's process dies.
- When no frame comes for 3 s (the stream stalled, the helper ended or hung), the robot starts
  **fresh helpers** for up to 10 s; one that sends a frame carries on. A drop like the one above
  costs a few seconds instead of the scan. A camera that never sent a frame still says it may be
  the wrong index; one that stopped says to check its cable.
- `pasr hardware list` and the Setup page's camera list and head-camera finder open each camera
  in a helper too, so the robot's process never holds a stale device list.
- Every warning and error the robot logs, and any error nothing caught on its event loop,
  becomes a **notice** (`pasr.orchestration.notices`); the dashboard shows each once as a toast
  on whatever page is open. An error without a message says "an unknown error occurred" (with
  its type). Notices are kept in memory only; the event log stays labels and numbers.

**Consequences.**
- Opening the camera starts a Python process (about 0.2 s on top of the camera's own start).
- The robot also logs at INFO level while it runs, so good news (a camera that is back) can be a
  toast; the terminal shows what it showed before.
- The cable still needs fixing: a reconnect cannot help a camera that stays off USB, and the
  frames during a drop are lost.
- Tests run the real helper in a process with a stand-in cv2 (`tests/support/camera_helper.py`)
  and never open a real camera.

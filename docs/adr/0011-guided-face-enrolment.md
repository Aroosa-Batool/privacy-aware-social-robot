# 0011 , Guided face enrolment

**Status:** accepted

**Context.** Face enrolment kept the first five frames with exactly one face. The detector runs
as fast as the CPU allows, so the five samples arrived within about half a second: five near
copies of one frontal view, in one light, with one expression. The room scan then sees the owner
from the side, from below and in other light, where none of the samples is close, and the owner
can look like a stranger. The owner also had no idea what to do, or when it was over.

**Decisions.**
- The robot **speaks a request for each pose** in `identity.enroll_face_poses` (default front,
  left, right, up, down, always in that order) and gives the owner `SETTLE_SECONDS` (1 s) to
  move before frames count.
- While a pose brings no new image for `REMIND_SECONDS` (5 s), the robot **says what is
  wrong**, from the commonest reason frames went unused: "Please come a little closer to me",
  "I can see more than one face", "Please turn your head a bit further to your left", "Not
  quite so far, please", "The other way, please".
- It keeps `identity.enroll_face_samples` (4) images **per pose**, at least `SAMPLE_INTERVAL_S`
  (0.5 s) apart, so the images of one pose are not copies of one moment. A pose gets at most
  `identity.enroll_face_pose_seconds` (15 s). A pose that falls short is **asked for once
  more** at the end ("Let's try that one again"); the front pose at once.
- The images are **stored once the front pose came out**; a pose that fell short twice is left
  out, and the robot says which ("I could not see you turned to your right; capture your face
  again to add that"). Without the front pose nothing is stored, the capture stops after asking
  for it twice, and the robot says why and asks the owner to try once more. Voice enrolment
  also says how it went.
- Every pose is logged (`owner.face_pose`: images, frames, why frames went unused, median
  `turned` and `tilt`), and an enrolment that stored nothing as `owner.enrolment_failed`, so a
  failed attempt can be diagnosed from the event log.
- A frame is used only with **exactly one face in full view**: the room scan's rules
  (`scan.follow.min_face_px`, `min_score`, `edge_margin`), but how far the face may turn is the
  pose's to decide.
- The **pose is checked** from the detector's five landmarks (`domain/framing.py`): `yaw` (the
  signed `turned`) for front (at most 0.12) and left or right (0.15 to 0.8), and `tilt` (where
  the nose sits between the eye line and the mouth) for up and down, at least 0.05 away from the
  straight-ahead faces'. A face that misses says how (`PoseMiss`: turned, too little, too far,
  wrong way). Which image side is the owner's left is **not assumed**, so a mirrored
  camera works: all faces of a pose point the same way, the opposite of the opposite pose's.
  Without landmarks every face counts and only the spoken guidance remains.
- Calibration captures faces the same guided way, so owner and stranger scores cover the same
  views as the enrolled set; image folders stay unguided.
- The pauses and pose limits are constants, not settings; the number of poses, images per pose
  and time per pose are settings.

**Consequences.**
- Face enrolment takes about 30 seconds instead of under two, and stores up to 20 embeddings
  instead of 5. With `identity.aggregate: max` each probe is compared with its closest view; a
  pose left out only weakens matching from that side.
- The pose limits are estimates from face geometry. The first try on the robot (front, left, up
  and down taken, right never) led to the wider side range, the spoken coaching and keeping a
  partial result; `owner.face_pose` events show how far the owner actually turned, to tune them
  further. Up and down rely on small landmark shifts (about 10° of tilt); any pose can be
  dropped from `identity.enroll_face_poses`.
- Calibrations made before this change compared frontal probes with frontal samples; calibrate
  again after re-enrolling.
- The stand-in face plugin in the tests gives each kind of unclear view (cut off, turned one
  way, turned the other) its own direction, so enrolling the side views helps with side views
  only, as with a real model.

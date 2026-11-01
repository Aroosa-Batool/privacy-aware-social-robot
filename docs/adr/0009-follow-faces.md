# 0009 , Following a face with the head during the room scan

**Status:** accepted

**Context.** The room scan looks in fixed directions (left, front, right). A person standing
between two of them, near the edge of the image, or turned away gives a poor face embedding: the
owner can then look like a stranger, and a remembered bystander like a new one. The camera sits
in the head and the Ohbot's HEADTURN and HEADNOD motors take any position from 0 to 10, so the
head can move until the camera sees such a face in full.

**Decisions.**
- **Off by default** (`scan.follow.enabled`), so experiments can compare it with the fixed
  directions; every setting is on Settings › Hardware › Follow faces.
- A face is **in full view** when it keeps a margin from every edge, is wide enough, is detected
  confidently and is not turned away (the nose's offset from between the eyes, from the
  detector's five landmarks). Pure geometry in `domain/framing.py`.
- Only a face that is **not in full view and matches nobody** (owner, remembered or already found
  bystanders) is followed. A face in full view, or one that already clearly matches someone, is
  compared at once, so with every face in full view the scan behaves as before (all scenario
  tests also run with following on).
- The head **nudges** towards the face in proportion to its offset from the image centre
  (`RobotHead.nudge`, gains `turn_gain` / `nod_gain`, signs `invert_turn` / `invert_nod`), waits
  `scan.settle_seconds`, and looks again. In the next frame the followed face is the most similar
  one, or else the one nearest to where the move should have brought it: a cut-off face and its
  full view can embed quite differently.
- It stops once the face is in full view, after `scan.follow.seconds`, or after two frames
  without it. Then it **always compares** the best view it had (fail closed): following can only
  make a face clearer, never make it disappear. The nod is undone, and the scan moves on to the
  next direction.
- One `perception.face_followed` event per followed face: direction, whether it came into full
  view, the number of head moves and the seconds, for the thesis's measurements.

**Consequences.**
- The camera can stay on up to `scan.follow.seconds` longer per such face, and the robot visibly
  turns towards a bystander. Both belong in the study's information for participants
  (docs/PRIVACY.md).
- The gains and signs depend on the head and camera and must be tuned on the real robot
  (docs/HARDWARE_SETUP.md). With wrong signs the face is lost, which fails closed.
- Face plugins may now report landmarks (`FaceObservation.landmarks`); without them a face is
  never judged turned away. Plugins without a box are never followed.

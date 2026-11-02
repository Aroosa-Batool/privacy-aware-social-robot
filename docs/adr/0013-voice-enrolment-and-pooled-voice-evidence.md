# 0013 , Read-aloud voice enrolment and pooled voice evidence

**Status:** accepted

**Context.** Voice enrolment stopped after three speech segments of at least 1 s, as cut by the
voice-activity detector at every 0.3 s pause: as little as 3 to 6 s of speech, three noisy
embeddings. While listening, every segment of at least 1 s was compared with them on its own (the
best single match, `identity.aggregate: max`), and one segment below `identity.voice_threshold`
(0.35) meant someone else was present. On the robot the owner, alone, was taken for a bystander:
the owner's segments scored 0.37 to 0.71 against the three samples, so some fell just below the
threshold (0.27 to 0.33), and one such segment was enough. A voice remembered from one of those
segments (with the ask-once policy) then stood for every similar sound.

What the literature says, for ECAPA-TDNN-style text-independent speaker verification:
- Enrolment needs **20 to 30 s of speech** or more: Azure Speaker Recognition required at least
  20 s of speech after silence removal; NIST SRE enrols with about 60 s per segment, and more
  enrolment always helped.
- **Short test segments are unreliable**, and far-field ones much more so: ECAPA's equal error
  rate on VoxCeleb1 rises from about 1 % at full length to 5 to 7 % at 1 s, and on the far-field
  VOiCES set from 4.8 % to 18.5 % at 1 s. ECAPA is trained on 2 s crops.
- Enrolment samples are best combined by **averaging their embeddings** (mean); no evaluation
  of the best single match (max) over samples was found.
- A **mismatch in speaking style** (read vs conversational speech) between enrolment and test
  makes verification substantially worse.
- SpeechBrain's own default threshold for this model is 0.25; 0.35 is stricter.

**Decisions.**
- Voice enrolment is **guided**: the robot asks the owner to read a text aloud, shown on the
  Profile page and printed by `pasr setup` (`VOICE_PASSAGE`: Aesop's *The North Wind and the
  Sun*, V. S. Vernon Jones's 1912 translation, public domain, the passage phoneticians use to
  show the sounds of a language), "until I stop you", then to tell it about their day in their
  own words: `READ_SHARE` (two thirds) of the speech is read, the rest free, so both speaking
  styles are covered. The microphone is closed while the robot speaks.
- It collects **`identity.enroll_voice_seconds` (30 s) of speech** (segments of at least
  `identity.min_voice_segment_seconds`), within `identity.enroll_timeout_seconds` (120 s, split
  like the speech), and stores it as **samples of about `VOICE_CHUNK_SECONDS` (4 s)**:
  consecutive segments joined without their pauses.
- A sample **unlike the others** (its similarity to the average of the others below the voice
  threshold: a noise, someone else talking) is left out. At least `MIN_VOICE_SAMPLES` (3) must
  remain, or nothing is stored and the robot says so.
- Voices are compared with a person's samples by their **averaged embedding**
  (`identity.voice_aggregate: mean`); faces keep `identity.aggregate: max`, which suits samples
  of different poses (ADR 0011).
- While listening, each segment is still identified on its own, but a voice other than the
  owner's **counts only once `identity.min_nonowner_seconds` (3 s) of its speech is heard**,
  pooled over its segments (they are grouped by voice as before). Its speech is then judged
  **together**: if the average of its embeddings matches the owner, it was the owner, and the
  robot listens on. A voice heard for less is dropped, not remembered and not asked about.
- Every `perception.voice` event carries the segment's length (`seconds`) and loudness
  (`level`, dBFS), and each pooled judgement is logged as `perception.voice_pooled`; voice
  enrolment logs the seconds of speech, the samples left out and how alike the stored ones are.
  The audio is still never stored, so a wrong decision can be diagnosed from these numbers.

**Consequences.**
- Voice enrolment takes about a minute instead of a few seconds. Voices enrolled before this
  change (three 1 s samples) still work, but should be captured again; calibrate again after.
- **Privacy trade-off:** someone who says less than 3 s in the whole listening window is not
  detected by voice (before: 1 s). With the camera allowed, the room scan still looks for them;
  with audio-only detection they are missed. `identity.min_nonowner_seconds: 1` restores the old
  sensitivity, with its false alarms.
- A voice is decided later: after 3 s of its speech instead of its first segment.
- Settings renamed: `identity.enroll_voice_samples` → `enroll_voice_seconds`,
  `identity.min_nonowner_segments` → `min_nonowner_seconds`; profiles that set the old names
  must be updated.
- The 0.35 threshold is unchanged; comparing with the averaged samples raises the owner's
  scores, and the Calibration page measures where the threshold should sit with this microphone
  and room.
- Inferences, not measured: the 4 s sample length, the read/free split and the 3 s evidence rule
  follow from the sources but were not tuned on this robot.

**Sources.**
- Azure Speaker Recognition, text-independent enrolment and its limits (retired service):
  <https://learn.microsoft.com/en-us/legal/cognitive-services/speech-service/speaker-recognition/characteristics-and-limitations-speaker-recognition>
- NIST SRE16 evaluation plan:
  <https://www.nist.gov/system/files/documents/2016/10/07/sre16_eval_plan_v1.3.pdf>; and
  <https://arxiv.org/abs/2204.10228>
- ECAPA-TDNN: <https://arxiv.org/abs/2005.07143>; short and far-field test durations:
  <https://arxiv.org/html/2601.13999>, <https://arxiv.org/abs/2310.04681>,
  <https://arxiv.org/html/2406.02167>
- Speaking-style mismatch: <https://arxiv.org/abs/2008.03617>
- Combining enrolment embeddings: <https://arxiv.org/abs/2206.11699>,
  <https://arxiv.org/abs/2209.00485>
- SpeechBrain `SpeakerRecognition.verify_batch` (threshold 0.25):
  <https://speechbrain.readthedocs.io/en/stable/API/speechbrain.inference.speaker.html>
- The passage: <https://www.gutenberg.org/ebooks/11339>

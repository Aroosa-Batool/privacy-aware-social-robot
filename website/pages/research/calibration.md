---
title: Calibrate thresholds
description: A similarity threshold decides who counts as the owner. Calibration measures the owner against fresh samples of themselves and of other people, and suggests the threshold between them.
---

Face and voice matching compare an embedding with the owner's enrolled ones by cosine
similarity. At or above `identity.face_threshold` (or `voice_threshold`) the person is the owner;
below it, someone else. Thresholds are **model-specific**: 0.40 suits InsightFace, 0.35 suits
SpeechBrain ECAPA, 0.75 suits Resemblyzer. After changing a model, enrol and calibrate again.

## Run it

```bash
uv run pasr calibrate voice --others 1 --apply   # owner, then one other person, live
uv run pasr calibrate face  --others 2           # shows the result, asks before saving
uv run pasr calibrate face  --others 0           # owner only: a conservative margin
uv run pasr calibrate voice --live-view          # watch each sample's similarity
```

The robot must be enrolled first. It captures as many samples per person as enrolment uses
(`--samples` to change that), scores each one **exactly** as the reminder flow would
(`identity.identify` with the configured aggregate), prints the distributions and suggests a
threshold. `--apply` saves it without asking; a running robot applies it on restart.

## From recordings

```bash
uv run pasr calibrate voice --wav owner.wav --wav friend.wav --fast
uv run pasr calibrate face --images ~/exp/owner --images ~/exp/friend
```

The first file or folder is the owner, the rest are other people. `--fast` does not pace WAV files
in real time. The recordings stay where they are; nothing is copied.

## How the threshold is chosen

| Measured | Suggested threshold |
|---|---|
| Owner and at least one other person | The point that balances false accepts and false rejects (the equal error rate). |
| Owner only | 0.10 below the owner's 10th-percentile score: conservative, so strangers rarely pass. |

The result also gets a verdict from the equal error rate: **good** (≤ 5%), **fair** (≤ 15%),
**poor**, or **insufficient** with fewer than 5 owner samples.

:::privacy Calibration stores one number
Other people's samples are scored against the owner and dropped. Only the chosen threshold is
saved, to `settings.json`, and the event log records only the modality, the plugin and the
threshold (`identity.calibrated`). ([ADR 0005](/decisions/0005-file-sources-and-calibration))
:::

## Model tests on your own recordings

```bash
PASR_TEST_WAV_OWNER=owner.wav PASR_TEST_WAV_OTHER=friend.wav \
PASR_TEST_IMAGES_OWNER=~/exp/owner PASR_TEST_IMAGES_OTHER=~/exp/friend \
  uv run pytest -m models
```

runs the real plugins over the recordings and checks that the owner scores above the threshold
and the other person below it.

---
title: Models
description: Choose the algorithm for each stage of an experiment, grouped by what the robot hears, what it sees, and how it judges whether a reminder is sensitive.
---

::image src=/assets/media/models.webp alt="The Models page, Voice tab: Silero for voice-activity detection, SpeechBrain ECAPA for voice recognition and faster-whisper for speech-to-text." url=localhost:8501/models caption="Each stage lists every registered plugin with its licence and what it needs."

Install the weights first on [Setup](/dashboard/setup). Changes take effect with **Save**;
**Discard** throws them away.

## Voice

| Stage | Default | Alternatives |
|---|---|---|
| **Voice-activity detection** | `silero`: Silero VAD, a neural detector (MIT, needs torch) | `energy`: an RMS threshold, no model, fine in quiet rooms |
| **Voice recognition** | `speechbrain_ecapa`: SpeechBrain ECAPA-TDNN speaker verification | `resemblyzer`: a lighter d-vector model (`uv sync --extra resemblyzer`) |
| **Speech-to-text** | `faster_whisper`: local Whisper on CTranslate2 | |

## Face

| Stage | Default |
|---|---|
| **Face recognition** | `insightface`: InsightFace `buffalo_l` (SCRFD detector and ArcFace) on onnxruntime. The weights are licensed for **non-commercial research only**. |

## Sensitivity

::image src=/assets/media/models-sensitivity.webp alt="The Sensitivity tab: the zero-shot classifier selected, with an editable list of sensitive topics." url=localhost:8501/models

| Plugin | How it decides |
|---|---|
| `zero_shot` (default) | A zero-shot DeBERTa-v3 model asks, for each topic, whether *"This reminder is about {topic}."* follows from the title. Runs locally; weights downloaded once. |
| `keyword` | Word lists: *doctor*, *dentist*, *bank*, *lawyer*, … are sensitive; *groceries*, *gym*, *call mum*, … are not. |

The page lets you edit the **sensitive topics** (zero-shot) or the **keyword lists**. The default
topics:

- health, illness or a medical appointment
- mental health or therapy
- medication or a prescription
- pregnancy, sex or contraception
- addiction treatment or recovery
- debt or owing money
- a bank or a bank account
- taxes or a salary
- a lawyer, a court or the police
- immigration, a visa or a residence permit
- divorce or a relationship problem
- a job interview or applying for a job
- a password or a PIN

The topics are worded for the model: *addiction treatment or recovery* flags rehab and AA
meetings but not *drinks with friends*, which the word *alcohol* would.

## All models, including planned ones

The expander at the bottom lists every registered plugin with its stage, whether its
dependencies are installed, and whether its weights are present.

:::warning Changing the face or voice model
Embeddings from different models are never compared. After switching the face or voice model,
capture the owner again on [Profile](/dashboard/profile) and
[re-calibrate the threshold](/research/calibration): a threshold that suits one model means
nothing for another (recommended starting points: InsightFace 0.40, ECAPA 0.35, Resemblyzer 0.75).
:::

Thresholds and other numeric parameters are not on this page; set them with
`pasr config set` or `pasr calibrate`. To add your own algorithm, see
[Swap algorithms](/research/algorithms).

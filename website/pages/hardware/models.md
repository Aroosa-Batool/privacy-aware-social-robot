---
title: Models
nav: Models & downloads
description: Download the model weights once; after that everything runs offline. Where they go, what each costs, and how to check them.
---

```bash
uv run pasr models status            # installed? weights downloaded?
uv run pasr models download          # load the configured models once
uv run pasr models download --kind face --kind speaker
```

or tick them on [Setup](/dashboard/setup) and click **Install the marked models**.

| Stage | Default plugin | Weights | Where |
|---|---|---|---|
| Face | `insightface` | `buffalo_l`, downloaded on first use | `models/insightface/` |
| Voice | `speechbrain_ecapa` | `spkrec-ecapa-voxceleb` from the Hugging Face hub | `models/speechbrain/` |
| Speech-to-text | `faster_whisper` | `base` from the Hugging Face hub | `models/faster-whisper/` |
| Sensitivity | `zero_shot` | `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` | `models/transformers/` |
| Voice activity | `silero` | inside the `silero-vad` package | |
| Voice (optional) | `resemblyzer` | inside the `resemblyzer` package | |

`models/` (`storage.models_dir`) is git-ignored and must not be inside `data/`; a settings
validator enforces that.

:::privacy The only time the robot uses the network
Downloading weights is the one deliberate network access. Nothing else opens a connection.
InsightFace is loaded with `allowed_modules=["detection", "recognition"]`, so its age and gender
model is never loaded.
:::

## Lazy loading

Plugins construct cheaply and load their model on first use, under their own lock, so listing or
configuring them never imports torch or onnxruntime. The first sensitive reminder after a start
therefore takes a few seconds longer while the models load.

## Licences

InsightFace's `buffalo_l` weights are for **non-commercial research only**: fine for a thesis,
to be revisited for any other use. The others are MIT or Apache-2.0. See
[Models and licences](/reference/models).

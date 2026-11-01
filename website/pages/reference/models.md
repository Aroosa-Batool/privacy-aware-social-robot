---
title: Models and licences
nav: Models & licences
description: Every registered plugin, what it needs, its recommended threshold, and the licence of its weights.
---

## Plugins

| Stage | Plugin | What it is | Needs | Threshold |
|---|---|---|---|---|
| Face | `insightface` | InsightFace `buffalo_l`: SCRFD detector and ArcFace embedder, on onnxruntime | insightface, onnxruntime, opencv | 0.40 |
| Speaker | `speechbrain_ecapa` | SpeechBrain ECAPA-TDNN speaker verification (`spkrec-ecapa-voxceleb`) | speechbrain, torch, torchaudio | 0.35 |
| Speaker | `resemblyzer` | Resemblyzer d-vector; light, weights in the package | resemblyzer, torch (`--extra resemblyzer`) | 0.75 |
| Voice activity | `silero` | Silero VAD neural detector | silero-vad, torch | |
| Voice activity | `energy` | RMS energy threshold, no model; for quiet rooms | | |
| Speech-to-text | `faster_whisper` | Whisper `base` on CTranslate2 | faster-whisper | |
| Sensitivity | `zero_shot` | DeBERTa-v3 zero-shot classification against a topic list | transformers, torch | |
| Sensitivity | `keyword` | Sensitive and non-sensitive word lists | | |
| Date and time | `dateparser` | Regex time extraction and the dateparser library for dates | dateparser | |

The threshold is each plugin's `recommended_threshold`, a starting point for
[calibration](/research/calibration).

## Licences

| Weights | Licence |
|---|---|
| InsightFace `buffalo_l` | **Non-commercial research only.** Fine for a thesis; must be revisited for any other use. |
| SpeechBrain `spkrec-ecapa-voxceleb` | Apache-2.0 (trained on VoxCeleb; check its terms for other uses). |
| faster-whisper `base` | MIT |
| `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` | MIT. It reads only the reminder title, on the laptop. |
| Resemblyzer | MIT |
| Silero VAD | MIT |

The code of this repository is MIT licensed.

## Where the weights go

Into `models/` (`storage.models_dir`), git-ignored and never inside `data/`. See
[Models and downloads](/hardware/models).

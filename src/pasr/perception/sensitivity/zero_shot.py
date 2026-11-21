"""Local zero-shot sensitivity classifier: a natural-language-inference model judges, for each
sensitive topic, whether "This reminder is about <topic>." follows from the reminder's title.

Weights come from the Hugging Face hub once into ``<models_dir>/transformers/`` and are loaded
from there offline afterwards. The title never leaves the laptop and is not logged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from pasr.paths import resolve
from pasr.perception.lazy import LazyEngine
from pasr.perception.protocols import SensitivityResult
from pasr.settings.tiers import setting

DEFAULT_TOPICS = [
    "health, illness or a medical appointment",
    "mental health or therapy",
    "medication or a prescription",
    "pregnancy, sex or contraception",
    "addiction treatment or recovery",
    "debt or owing money",
    "a bank or a bank account",
    "taxes or a salary",
    "a lawyer, a court or the police",
    "immigration, a visa or a residence permit",
    "divorce or a relationship problem",
    "a job interview or applying for a job",
    "a password or a PIN",
]
"""Worded for the model: e.g. "addiction treatment or recovery" flags rehab and AA meetings but
not "drinks with friends", which "alcohol" would."""


class ZeroShotSensitivityClassifier(LazyEngine):
    class Params(BaseModel):
        sensitive_topics: list[str] = setting(
            tier="advanced",
            default_factory=lambda: list(DEFAULT_TOPICS),
            description="A reminder about any of these topics is sensitive.",
        )
        threshold: float = setting(
            0.5,
            tier="advanced",
            ge=0,
            le=1,
            description="How sure the model must be that a reminder is about a sensitive topic.",
        )
        template: str = setting(
            "This reminder is about {}.",
            tier="advanced",
            pattern=r".*\{\}.*",
            description="Sentence the model checks for each topic; {} is the topic.",
        )
        model: str = setting(
            "MoritzLaurer/deberta-v3-base-zeroshot-v2.0",
            tier="advanced",
            description="Hugging Face id of a zero-shot (natural-language-inference) model.",
        )
        models_dir: Path = setting(
            Path("models"),
            tier="advanced",
            description="Where the model is downloaded (storage.models_dir by default).",
        )
        threads: int = setting(2, tier="advanced", ge=1, le=16, description="torch CPU threads.")

    def __init__(self, params: Params) -> None:
        super().__init__()
        self.params = params

    def classify(self, text: str) -> SensitivityResult:
        topics = [t.strip() for t in self.params.sensitive_topics if t.strip()]
        if not text.strip() or not topics:
            return SensitivityResult(False, 0.0)
        scores = self._entailment(text, [self.params.template.format(t) for t in topics])
        ranked = sorted(zip(scores, topics, strict=True), reverse=True)
        best = ranked[0][0]
        reasons = tuple(topic for score, topic in ranked if score >= self.params.threshold)
        return SensitivityResult(best >= self.params.threshold, round(best, 3), reasons)

    # --- the only code that talks to transformers ----------------------------------------------

    def _entailment(self, premise: str, hypotheses: list[str]) -> list[float]:
        """Probability that each hypothesis follows from the premise."""
        import torch

        tokenizer, model, entails, contradicts = self._engine_or_load()
        with self._lock, torch.inference_mode():
            batch = tokenizer(
                [premise] * len(hypotheses),
                hypotheses,
                return_tensors="pt",
                padding=True,
                truncation=True,
            )
            logits = np.asarray(model(**batch).logits.cpu().numpy(), dtype=np.float64)
        pair = logits[:, [contradicts, entails]]
        pair = np.exp(pair - pair.max(axis=1, keepdims=True))
        return [float(p) for p in pair[:, 1] / pair.sum(axis=1)]

    def _load(self) -> Any:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        torch.set_num_threads(self.params.threads)
        cache = resolve(self.params.models_dir) / "transformers"
        cache.mkdir(parents=True, exist_ok=True)

        def load(local_files_only: bool) -> tuple[Any, Any]:
            options = {"cache_dir": str(cache), "local_files_only": local_files_only}
            return (
                AutoTokenizer.from_pretrained(self.params.model, **options),
                AutoModelForSequenceClassification.from_pretrained(self.params.model, **options),
            )

        try:
            tokenizer, model = load(local_files_only=True)
        except OSError:  # not downloaded yet: this is the one-time download
            tokenizer, model = load(local_files_only=False)
        model.eval()
        labels = {name.lower(): index for name, index in model.config.label2id.items()}
        entails = next(i for name, i in labels.items() if name.startswith("entail"))
        contradicts = next(
            (i for name, i in labels.items() if name.startswith("contradict")),
            next(i for i in labels.values() if i != entails),
        )
        return tokenizer, model, entails, contradicts

from __future__ import annotations

from pasr.domain.media import AudioChunk, SpeechSegment


class SpeechSegmenter:
    """Groups audio chunks into speech segments using per-chunk speech probabilities."""

    def __init__(
        self,
        *,
        speech_threshold: float,
        min_speech_ms: int,
        min_silence_ms: int,
        max_segment_seconds: float,
    ) -> None:
        self.speech_threshold = speech_threshold
        self.min_speech_s = min_speech_ms / 1000
        self.min_silence_s = min_silence_ms / 1000
        self.max_segment_s = max_segment_seconds
        self._speech: list[AudioChunk] = []
        self._trailing_silence: list[AudioChunk] = []

    def push(self, chunk: AudioChunk, speech_probability: float) -> list[SpeechSegment]:
        if speech_probability >= self.speech_threshold:
            self._speech.extend(self._trailing_silence)
            self._trailing_silence.clear()
            self._speech.append(chunk)
            span = (self._speech[-1].end - self._speech[0].start).total_seconds()
            return self._close() if span >= self.max_segment_s else []
        if not self._speech:
            return []
        self._trailing_silence.append(chunk)
        silence = sum(c.duration_s for c in self._trailing_silence)
        return self._close() if silence >= self.min_silence_s else []

    def flush(self) -> list[SpeechSegment]:
        return self._close()

    def _close(self) -> list[SpeechSegment]:
        speech, self._speech = self._speech, []
        self._trailing_silence.clear()
        if not speech:
            return []
        segment = SpeechSegment.from_chunks(speech)
        return [segment] if segment.duration_s >= self.min_speech_s else []

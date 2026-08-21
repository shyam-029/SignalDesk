# FinBERT sentiment scorer.
#
# Uses the ProsusAI/finbert model (financial-domain BERT) via transformers.
# The model is loaded LAZILY and cached: first call downloads (~420MB, cached by
# huggingface) and loads the pipeline; subsequent calls reuse the cached instance.
# Scoring runs in a worker thread (transformers is synchronous) to keep the event
# loop responsive.
#
# New concepts:
#  - Lazy singleton: the heavy ML model is loaded on first use, not at import,
#    so tests that never call it stay fast and network-free.

import asyncio
import threading
from dataclasses import dataclass

MODEL_NAME = "ProsusAI/finbert"


@dataclass(frozen=True)
class Sentiment:
    """Sentiment result for a piece of text."""

    label: str  # "positive" | "negative" | "neutral"
    score: float  # confidence 0..1 for the predicted label


class FinBERTScorer:
    """FinBERT sentiment scorer with a cached, lazily-loaded pipeline."""

    _pipeline = None
    _lock = threading.Lock()

    @classmethod
    def _get_pipeline(cls):
        """Load (once) and cache the transformers pipeline, thread-safely.

        Multiple ingest workers (asyncio.to_thread) may call this concurrently;
        the lock ensures only one thread performs the first import/load.
        """
        if cls._pipeline is None:
            with cls._lock:
                if cls._pipeline is None:
                    from transformers import pipeline

                    cls._pipeline = pipeline(
                        "sentiment-analysis", model=MODEL_NAME, top_k=None
                    )
        return cls._pipeline

    def score_text(self, text: str) -> Sentiment:
        """Score a single text; returns the label with the highest confidence."""
        pipe = self._get_pipeline()
        results = pipe([text])[0]
        best = max(results, key=lambda r: r["score"])
        return Sentiment(label=best["label"], score=round(float(best["score"]), 4))

    async def score_text_async(self, text: str) -> Sentiment:
        """Score a text off the event loop (transformers is synchronous)."""
        return await asyncio.to_thread(self.score_text, text)
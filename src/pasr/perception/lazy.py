"""Shared shape of the ML plugins: cheap to construct, model loaded on first use."""

from __future__ import annotations

import threading
from typing import Any, ClassVar

from pasr.perception.registry import PluginUnavailableError


class LazyEngine:
    """Loads the heavy model on first use under a lock, and turns a missing library into a
    ``PluginUnavailableError`` saying how to install it. Inference also runs under the lock
    because ``RobotContext.compute`` uses a thread pool."""

    extra: ClassVar[str] = "core"
    """``core`` for libraries in the main dependencies, else the name of the optional extra."""

    def __init__(self) -> None:
        self._engine: Any = None
        self._lock = threading.RLock()

    def warm_up(self) -> None:
        """Load (and, on first use, download) the model now instead of on the first frame."""
        self._engine_or_load()

    def _engine_or_load(self) -> Any:
        with self._lock:
            if self._engine is None:
                try:
                    self._engine = self._load()
                except ImportError as exc:
                    install = "uv sync" if self.extra == "core" else f"uv sync --extra {self.extra}"
                    raise PluginUnavailableError(
                        f"{type(self).__name__} cannot load its library ({exc}); run: {install}"
                    ) from exc
            return self._engine

    def _load(self) -> Any:
        raise NotImplementedError

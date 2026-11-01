"""Runs a ``Runtime`` on its own asyncio loop in a background thread.

Streamlit re-runs page scripts on every interaction, so the robot cannot live inside a script
run. The dashboard keeps one ``RuntimeHandle`` (``st.cache_resource``) and talks to the runtime
only through ``call`` / ``snapshot``; the runtime thread never touches Streamlit.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import Any

from pasr.orchestration.runtime import Runtime, RuntimeSnapshot
from pasr.settings.schema import Settings


class RuntimeHandle:
    def __init__(self, load_settings: Callable[[], Settings]) -> None:
        self._load_settings = load_settings
        self._runtime: Runtime | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._guard = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self._runtime is not None

    def start(self) -> None:
        with self._guard:
            if self.running:
                return
            runtime = Runtime(self._load_settings(), live_window=True)
            loop = asyncio.new_event_loop()
            started = threading.Event()
            failure: list[BaseException] = []

            def main() -> None:
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(runtime.start())
                except BaseException as exc:
                    failure.append(exc)
                    started.set()
                    loop.close()
                    return
                started.set()
                try:
                    loop.run_forever()
                finally:
                    loop.run_until_complete(runtime.stop())
                    loop.close()

            thread = threading.Thread(target=main, name="pasr-runtime", daemon=True)
            thread.start()
            started.wait()
            if failure:
                raise failure[0]
            self._runtime, self._loop, self._thread = runtime, loop, thread

    def stop(self, timeout: float = 15.0) -> None:
        with self._guard:
            loop, thread = self._loop, self._thread
            if loop is None or thread is None:
                return
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout)
            self._runtime = self._loop = self._thread = None

    def call[T](self, fn: Callable[[Runtime], Coroutine[Any, Any, T]], timeout: float = 60.0) -> T:
        """Run ``fn(runtime)`` on the runtime's loop and wait for the result."""
        runtime, loop = self._runtime, self._loop
        if runtime is None or loop is None:
            raise RuntimeError("the robot runtime is not running")
        return asyncio.run_coroutine_threadsafe(fn(runtime), loop).result(timeout)

    def call_sync[T](self, fn: Callable[[Runtime], T], timeout: float = 10.0) -> T:
        async def wrapper(runtime: Runtime) -> T:
            return fn(runtime)

        return self.call(wrapper, timeout)

    def snapshot(self) -> RuntimeSnapshot | None:
        if not self.running:
            return None
        return self.call_sync(lambda runtime: runtime.snapshot())

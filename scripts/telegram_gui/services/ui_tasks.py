from __future__ import annotations

import threading
from typing import Any, Callable


class UiTaskService:
    def __init__(self, *, idle_add: Callable[..., Any]):
        self._idle_add = idle_add

    def start(
        self,
        *,
        worker: Callable[[], Any],
        on_success: Callable[[Any], Any],
        on_error: Callable[[Exception], Any],
    ) -> threading.Thread:
        def run() -> None:
            try:
                result = worker()
            except Exception as exc:  # pragma: no cover - exercised through callers
                self._idle_add(on_error, exc)
                return
            self._idle_add(on_success, result)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

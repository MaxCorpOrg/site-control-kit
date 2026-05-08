from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable


class TaskCancelled(RuntimeError):
    pass


class TaskController:
    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen[str]] = set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def attach_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.add(process)
        if self.cancel_requested:
            self._terminate_process(process)

    def detach_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.discard(process)

    def request_cancel(self) -> None:
        self._cancel_event.set()
        with self._lock:
            processes = list(self._processes)
        for process in processes:
            self._terminate_process(process)

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except OSError:
            return


@dataclass(frozen=True)
class ProcessRunResult:
    return_code: int
    stdout: str
    stderr: str
    stdout_lines: tuple[str, ...]
    stderr_lines: tuple[str, ...]
    timed_out: bool
    forced_cancel: bool
    cancel_requested: bool


class ProcessRunner:
    def run(
        self,
        args: list[str],
        *,
        cwd: str,
        timeout_sec: int | None,
        controller: TaskController | None = None,
        env: dict[str, str] | None = None,
        emit_stdout: Callable[[str], None] | None = None,
        emit_stderr: Callable[[str], None] | None = None,
        on_cancel_begin: Callable[[], None] | None = None,
        bufsize: int = 1,
    ) -> ProcessRunResult:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=bufsize,
        )
        if controller is not None:
            controller.attach_process(process)

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def _consume(
            stream: subprocess.Popen[str] | None,
            sink: list[str],
            emit: Callable[[str], None] | None,
            *,
            is_stderr: bool,
        ) -> None:
            actual = process.stderr if is_stderr else process.stdout
            assert actual is not None
            for line in actual:
                sink.append(line)
                text = line.rstrip()
                if emit is not None and text:
                    emit(text)

        stdout_thread = threading.Thread(
            target=_consume,
            args=(process, stdout_lines, emit_stdout),
            kwargs={"is_stderr": False},
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_consume,
            args=(process, stderr_lines, emit_stderr),
            kwargs={"is_stderr": True},
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        return_code, timed_out, forced_cancel, cancel_notified = self._wait_for_exit(
            process,
            timeout_sec=timeout_sec,
            controller=controller,
            on_cancel_begin=on_cancel_begin,
        )
        if controller is not None and controller.cancel_requested and not cancel_notified and on_cancel_begin is not None:
            on_cancel_begin()

        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        if controller is not None:
            controller.detach_process(process)

        return ProcessRunResult(
            return_code=return_code,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            stdout_lines=tuple(stdout_lines),
            stderr_lines=tuple(stderr_lines),
            timed_out=timed_out,
            forced_cancel=forced_cancel,
            cancel_requested=bool(controller and controller.cancel_requested),
        )

    def _wait_for_exit(
        self,
        process: subprocess.Popen[str],
        *,
        timeout_sec: int | None,
        controller: TaskController | None,
        on_cancel_begin: Callable[[], None] | None,
    ) -> tuple[int, bool, bool, bool]:
        deadline = time.monotonic() + max(timeout_sec, 1) if timeout_sec is not None else None
        cancel_deadline: float | None = None
        cancel_notified = False
        while True:
            return_code = process.poll()
            if return_code is not None:
                if controller is not None and controller.cancel_requested and not cancel_notified and on_cancel_begin is not None:
                    on_cancel_begin()
                    cancel_notified = True
                return return_code, False, False, cancel_notified
            now = time.monotonic()
            if controller is not None and controller.cancel_requested:
                if not cancel_notified and on_cancel_begin is not None:
                    on_cancel_begin()
                    cancel_notified = True
                if cancel_deadline is None:
                    cancel_deadline = now + 6.0
                    try:
                        process.terminate()
                    except OSError:
                        pass
                elif now >= cancel_deadline:
                    try:
                        process.kill()
                    except OSError:
                        pass
                    process.wait(timeout=1)
                    return process.returncode or -1, False, True, cancel_notified
            if deadline is not None and now >= deadline:
                try:
                    process.kill()
                except OSError:
                    pass
                process.wait(timeout=1)
                return process.returncode or -1, True, False, cancel_notified
            time.sleep(0.1)


class TaskRunner(ProcessRunner):
    pass

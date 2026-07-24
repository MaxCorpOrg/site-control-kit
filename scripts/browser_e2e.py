#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "site-control-e2e-token"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def api(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 10,
) -> dict[str, Any]:
    body = None
    headers = {
        "Accept": "application/json",
        "X-Access-Token": TOKEN,
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc


def wait_until(predicate, *, timeout: float, interval: float = 0.1, message: str):
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() <= deadline:
        try:
            value = predicate()
            if value:
                return value
        except (RuntimeError, URLError, ConnectionError) as exc:
            last_error = exc
        time.sleep(interval)
    detail = f": {last_error}" if last_error else ""
    raise TimeoutError(f"{message}{detail}")


class ExampleServer:
    def __init__(self, port: int):
        handler = lambda *args, **kwargs: SimpleHTTPRequestHandler(  # noqa: E731
            *args,
            directory=str(ROOT / "examples"),
            **kwargs,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class BrowserE2E:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.started_at = now_iso()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.output = Path(args.output or ROOT / "artifacts" / "e2e" / timestamp).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.workspace = Path(tempfile.mkdtemp(prefix="site-control-e2e-"))
        self.hub_port = free_port()
        self.site_port = free_port()
        self.debug_port = free_port()
        self.base_url = f"http://127.0.0.1:{self.hub_port}"
        self.page_url = f"http://127.0.0.1:{self.site_port}/agent-browser-smoke.html"
        self.hub: subprocess.Popen[str] | None = None
        self.chrome: subprocess.Popen[str] | None = None
        self.site = ExampleServer(self.site_port)
        self.steps: list[dict[str, Any]] = []
        self.timings_ms: list[float] = []
        self.recoveries = 0
        self.client_id = ""
        self.tab_id = 0
        self.session_id = ""
        self.chrome_binary = ""

    def record(self, name: str, action):
        started = time.monotonic()
        try:
            value = action()
        except Exception as exc:
            duration = (time.monotonic() - started) * 1000
            self.steps.append(
                {
                    "name": name,
                    "ok": False,
                    "duration_ms": round(duration, 2),
                    "error": str(exc),
                }
            )
            raise
        duration = (time.monotonic() - started) * 1000
        self.timings_ms.append(duration)
        self.steps.append(
            {
                "name": name,
                "ok": True,
                "duration_ms": round(duration, 2),
            }
        )
        return value

    def prepare_extension(self) -> Path:
        target = self.workspace / "extension"
        shutil.copytree(ROOT / "extension", target)
        background = target / "background.js"
        text = background.read_text(encoding="utf-8")
        text = text.replace(
            'serverUrl: "http://127.0.0.1:8765"',
            f'serverUrl: "http://127.0.0.1:{self.hub_port}"',
            1,
        )
        text = text.replace(
            'token: "local-bridge-quickstart-2026"',
            f'token: "{TOKEN}"',
            1,
        )
        background.write_text(text, encoding="utf-8")
        return target

    def start_hub(self) -> None:
        if self.hub and self.hub.poll() is None:
            return
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONPATH": str(ROOT),
                "SITECTL_RUNTIME_ROOT": str(self.workspace / "runtime"),
                "SITECTL_STATE_FILE": str(self.workspace / "state.json"),
                "SITECTL_RUNTIME_EVENTS_LOG": str(self.output / "hub-events.jsonl"),
                "SITECTL_RUNTIME_ERRORS_LOG": str(self.output / "hub-errors.jsonl"),
            }
        )
        hub_log = (self.output / "hub.log").open("a", encoding="utf-8")
        self.hub = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "webcontrol",
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.hub_port),
                "--token",
                TOKEN,
                "--state-file",
                str(self.workspace / "state.json"),
                "--lease-duration-ms",
                "60000",
                "--max-attempts",
                "3",
                "--artifacts-root",
                str(self.output / "sessions"),
            ],
            cwd=ROOT,
            env=environment,
            stdout=hub_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_until(
            lambda: api(self.base_url, "GET", "/health").get("ok"),
            timeout=10,
            message="Хаб не запустился",
        )

    def stop_hub(self) -> None:
        if not self.hub or self.hub.poll() is not None:
            return
        self.hub.send_signal(signal.SIGTERM)
        try:
            self.hub.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.hub.kill()
            self.hub.wait(timeout=5)

    def start_chrome(self, extension: Path) -> None:
        chrome_binary = (
            self.args.chrome
            or shutil.which("chromium")
            or shutil.which("chromium-browser")
            or shutil.which("google-chrome-for-testing")
        )
        if not chrome_binary:
            raise RuntimeError(
                "Не найден Chromium или Chrome for Testing. "
                "Запустите scripts/install_chrome_for_testing.py и передайте --chrome."
            )
        self.chrome_binary = str(chrome_binary)
        chrome_log = (self.output / "chrome.log").open("w", encoding="utf-8")
        command = [
            chrome_binary,
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            f"--user-data-dir={self.workspace / 'chrome-profile'}",
            f"--disable-extensions-except={extension}",
            f"--load-extension={extension}",
            f"--remote-debugging-port={self.debug_port}",
            "--window-size=1280,1000",
        ]
        if not self.args.headed:
            command.append("--headless=new")
        command.append(self.page_url)
        self.chrome = subprocess.Popen(
            command,
            stdout=chrome_log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def stop_chrome(self) -> None:
        if not self.chrome or self.chrome.poll() is not None:
            return
        self.chrome.terminate()
        try:
            self.chrome.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.chrome.kill()
            self.chrome.wait(timeout=5)

    def wait_client(self) -> None:
        def locate():
            response = api(self.base_url, "GET", "/api/clients")
            clients = [
                item
                for item in response.get("clients", [])
                if item.get("extension_version") == "0.2.0" and item.get("is_online")
            ]
            if not clients:
                return None
            client = clients[0]
            tab = next(
                (
                    item
                    for item in client.get("tabs", [])
                    if str(item.get("url") or "").startswith(self.page_url)
                ),
                None,
            )
            if not tab:
                return None
            return client, tab

        client, tab = wait_until(
            locate,
            timeout=25,
            interval=0.25,
            message="Расширение не подключилось к хабу",
        )
        self.client_id = str(client["client_id"])
        self.tab_id = int(tab["id"])

    def create_session(self) -> None:
        response = api(
            self.base_url,
            "POST",
            "/api/sessions",
            {
                "owner_id": "chrome-e2e",
                "client_id": self.client_id,
                "ttl_seconds": 600,
                "policy": {
                    "allowed_domains": ["127.0.0.1"],
                    "allow_input": True,
                    "allow_cdp": True,
                    "require_dangerous_confirmation": False,
                    "capture_screenshots": True,
                    "capture_console": True,
                    "capture_network": True,
                },
            },
        )
        self.session_id = str(response["session"]["session_id"])
        api(
            self.base_url,
            "POST",
            f"/api/sessions/{self.session_id}/locks",
            {
                "client_id": self.client_id,
                "tab_id": self.tab_id,
                "lock_mode": "exclusive",
            },
        )

    def command(
        self,
        command: dict[str, Any],
        *,
        tab_id: int | None = None,
        session: bool = True,
        retry_policy: str | None = None,
        timeout: float = 30,
    ) -> dict[str, Any]:
        response = api(
            self.base_url,
            "POST",
            "/api/commands",
            {
                "issued_by": "chrome-e2e",
                "timeout_ms": int(timeout * 1000),
                "lease_duration_ms": 60_000,
                "max_attempts": 3,
                "idempotency_key": str(uuid.uuid4()),
                "retry_policy": retry_policy,
                "session_id": self.session_id if session else None,
                "confirmation": {"confirmed": True},
                "target": {
                    "client_id": self.client_id,
                    "tab_id": int(tab_id or self.tab_id),
                },
                "command": command,
            },
        )
        command_id = str(response["command_id"])

        def terminal():
            current = api(self.base_url, "GET", f"/api/commands/{command_id}")["command"]
            if current.get("status") in {
                "completed",
                "failed",
                "partial",
                "cancelled",
                "expired",
                "dead_letter",
                "rejected",
            }:
                return current
            return None

        current = wait_until(
            terminal,
            timeout=timeout + 10,
            interval=0.1,
            message=f"Команда {command_id} не завершилась",
        )
        if current.get("status") != "completed":
            raise RuntimeError(
                f"Команда {command_id} завершилась со статусом {current.get('status')}: "
                f"{self.result(current).get('error')}"
            )
        return current

    def result(self, command: dict[str, Any]) -> dict[str, Any]:
        return command["deliveries"][self.client_id]["result"]

    def snapshot(self) -> dict[str, Any]:
        command = self.command(
            {
                "type": "snapshot",
                "include_frames": True,
                "limit": 300,
            },
            retry_policy="safe_retry",
        )
        return self.result(command)["data"]

    @staticmethod
    def find(snapshot: dict[str, Any], *, name: str, role: str | None = None) -> dict[str, Any]:
        matches = [
            item
            for item in snapshot.get("elements", [])
            if item.get("name") == name and (role is None or item.get("role") == role)
        ]
        if len(matches) != 1:
            raise AssertionError(f"Ожидался один элемент {name!r}, найдено {len(matches)}")
        return matches[0]

    def run_scenarios(self) -> None:
        initial = self.record("семантический снимок с фреймами", self.snapshot)
        if initial.get("frame_count", 0) < 3:
            raise AssertionError(f"Ожидалось минимум три фрейма: {initial.get('frame_count')}")

        name_field = self.find(initial, name="Имя агента", role="textbox")
        rerender = self.find(initial, name="Заменить поле в DOM", role="button")
        self.record(
            "перерисовка страницы",
            lambda: self.command(
                {
                    "type": "smart_click",
                    "locator": {"strategy": "ref", "value": rerender["ref"]},
                },
                retry_policy="never_retry",
            ),
        )
        healed = self.record(
            "восстановление ref после перерисовки",
            lambda: self.command(
                {
                    "type": "set_editable_text",
                    "locator": {"strategy": "ref", "value": name_field["ref"]},
                    "value": "Восстановлено",
                },
                retry_policy="retry_if_not_started",
            ),
        )
        if not self.result(healed)["data"].get("healed"):
            raise AssertionError("Расширение не подтвердило восстановление ref")

        self.record(
            "клик с доказательством изменения текста",
            lambda: self.command(
                {
                    "type": "smart_click",
                    "locator": {
                        "strategy": "role",
                        "value": "button",
                        "name": "Сохранить",
                        "exact": True,
                    },
                    "proof": {
                        "expected_text": "Готово: Восстановлено",
                        "timeout_ms": 5000,
                    },
                },
                retry_policy="never_retry",
            ),
        )

        self.record(
            "открытый Shadow DOM",
            lambda: self.command(
                {
                    "type": "smart_click",
                    "locator": {
                        "strategy": "role",
                        "value": "button",
                        "name": "Кнопка в Shadow DOM",
                        "exact": True,
                    },
                },
                retry_policy="never_retry",
            ),
        )
        self.record(
            "ожидание результата в Shadow DOM",
            lambda: self.command(
                {
                    "type": "wait_for",
                    "locator": {
                        "strategy": "text",
                        "value": "Готово: Shadow DOM",
                        "exact": True,
                    },
                    "state": "visible",
                    "timeout_ms": 5000,
                },
                retry_policy="safe_retry",
            ),
        )

        refreshed = self.record("повторный снимок", self.snapshot)
        frame_field = self.find(refreshed, name="Значение во фрейме", role="textbox")
        frame_button = self.find(refreshed, name="Сохранить во фрейме", role="button")
        nested_button = self.find(
            refreshed,
            name="Действие во вложенном фрейме",
            role="button",
        )
        self.record(
            "ввод в iframe",
            lambda: self.command(
                {
                    "type": "set_editable_text",
                    "locator": {"strategy": "ref", "value": frame_field["ref"]},
                    "value": "Iframe работает",
                },
                retry_policy="retry_if_not_started",
            ),
        )
        self.record(
            "клик в iframe",
            lambda: self.command(
                {
                    "type": "smart_click",
                    "locator": {"strategy": "ref", "value": frame_button["ref"]},
                    "proof": {"expected_text": "Фрейм: Iframe работает"},
                },
                retry_policy="never_retry",
            ),
        )
        self.record(
            "клик во вложенном iframe",
            lambda: self.command(
                {
                    "type": "smart_click",
                    "locator": {"strategy": "ref", "value": nested_button["ref"]},
                    "proof": {"expected_text": "Вложенное действие выполнено"},
                },
                retry_policy="never_retry",
            ),
        )

        screenshot_path = self.output / "full-page.png"
        screenshot = self.record(
            "полноразмерный снимок",
            lambda: self.command(
                {"type": "screenshot", "full_page": True},
                retry_policy="safe_retry",
            ),
        )
        data_url = str(self.result(screenshot)["data"]["imageDataUrl"])
        import base64

        screenshot_path.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))

        self.record("конфликт блокировок двух агентов", self.verify_lock_conflict)
        self.record("восстановление MV3 service worker", self.verify_service_worker_restart)
        self.record("очередь результата после перезапуска хаба", self.verify_hub_restart)

    def debug_targets(self) -> list[dict[str, Any]]:
        with urlopen(f"http://127.0.0.1:{self.debug_port}/json/list", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, list) else []

    def verify_service_worker_restart(self) -> None:
        target = wait_until(
            lambda: next(
                (
                    item
                    for item in self.debug_targets()
                    if item.get("type") == "service_worker"
                    and str(item.get("url") or "").startswith("chrome-extension://")
                ),
                None,
            ),
            timeout=10,
            message="Не найден service worker расширения",
        )
        target_id = str(target["id"])
        with urlopen(
            Request(
                f"http://127.0.0.1:{self.debug_port}/json/close/{target_id}",
                method="PUT",
            ),
            timeout=5,
        ):
            pass
        wait_until(
            lambda: all(str(item.get("id")) != target_id for item in self.debug_targets()),
            timeout=10,
            message="Старый service worker не остановился",
        )
        snapshot = self.command(
            {"type": "snapshot", "include_frames": True, "limit": 50},
            retry_policy="safe_retry",
            timeout=35,
        )
        if not self.result(snapshot).get("ok"):
            raise AssertionError("Команда не выполнилась после перезапуска service worker")
        self.recoveries += 1

    def verify_lock_conflict(self) -> None:
        second = api(
            self.base_url,
            "POST",
            "/api/sessions",
            {
                "owner_id": "second-agent",
                "client_id": self.client_id,
                "ttl_seconds": 120,
                "policy": {"require_dangerous_confirmation": False},
            },
        )["session"]
        try:
            api(
                self.base_url,
                "POST",
                f"/api/sessions/{second['session_id']}/locks",
                {
                    "client_id": self.client_id,
                    "tab_id": self.tab_id,
                    "lock_mode": "exclusive",
                },
            )
        except RuntimeError as exc:
            if "session_conflict" not in str(exc):
                raise
        else:
            raise AssertionError("Вторая сессия получила уже заблокированную вкладку")

    def verify_hub_restart(self) -> None:
        response = api(
            self.base_url,
            "POST",
            "/api/commands",
            {
                "issued_by": "chrome-e2e",
                "timeout_ms": 30_000,
                "lease_duration_ms": 60_000,
                "idempotency_key": str(uuid.uuid4()),
                "retry_policy": "safe_retry",
                "session_id": self.session_id,
                "target": {"client_id": self.client_id, "tab_id": self.tab_id},
                "command": {
                    "type": "wait_for",
                    "locator": {
                        "strategy": "text",
                        "value": "Этот текст не появится",
                        "exact": True,
                    },
                    "state": "visible",
                    "timeout_ms": 2500,
                },
            },
        )
        command_id = str(response["command_id"])
        wait_until(
            lambda: (
                api(self.base_url, "GET", f"/api/commands/{command_id}")["command"].get("status")
                == "running"
            ),
            timeout=10,
            message="Команда не перешла в running",
        )
        self.stop_hub()
        time.sleep(3)
        self.start_hub()
        final = wait_until(
            lambda: self._terminal_command(command_id),
            timeout=20,
            interval=0.2,
            message="Сохранённый результат не вернулся после перезапуска хаба",
        )
        if final.get("status") != "failed":
            raise AssertionError(
                f"Ожидался обработанный failed result, получено {final.get('status')}"
            )
        self.recoveries += 1

    def _terminal_command(self, command_id: str) -> dict[str, Any] | None:
        current = api(self.base_url, "GET", f"/api/commands/{command_id}")["command"]
        if current.get("status") in {
            "completed",
            "failed",
            "cancelled",
            "expired",
            "dead_letter",
        }:
            return current
        return None

    def report(self, status: str, error: str | None = None) -> Path:
        sorted_times = sorted(self.timings_ms)
        p95 = 0.0
        if sorted_times:
            index = max(
                0, min(len(sorted_times) - 1, int(round(0.95 * len(sorted_times) + 0.5)) - 1)
            )
            p95 = sorted_times[index]
        payload = {
            "status": status,
            "started_at": self.started_at,
            "finished_at": now_iso(),
            "base_main_sha": os.getenv("SITE_CONTROL_BASE_MAIN_SHA", ""),
            "chrome_binary": self.chrome_binary,
            "client_id": self.client_id,
            "tab_id": self.tab_id,
            "session_id": self.session_id,
            "steps": self.steps,
            "metrics": {
                "test_count": len(self.steps),
                "passed": sum(1 for item in self.steps if item.get("ok")),
                "failed": sum(1 for item in self.steps if not item.get("ok")),
                "average_command_ms": round(statistics.mean(self.timings_ms), 2)
                if self.timings_ms
                else 0,
                "p95_command_ms": round(p95, 2),
                "lost_acknowledged_commands": 0 if status == "passed" else None,
                "duplicate_dangerous_actions": 0 if status == "passed" else None,
                "recoveries": self.recoveries,
            },
            "error": error,
        }
        path = self.output / "report.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def run(self) -> int:
        try:
            extension = self.prepare_extension()
            self.site.start()
            self.start_hub()
            self.start_chrome(extension)
            self.record("подключение расширения", self.wait_client)
            self.record("создание сессии и блокировки", self.create_session)
            self.run_scenarios()
        except Exception as exc:
            report = self.report("failed", str(exc))
            print(f"E2E завершён с ошибкой: {exc}", file=sys.stderr)
            print(f"Отчёт: {report}", file=sys.stderr)
            return 1
        finally:
            try:
                if self.session_id and self.hub and self.hub.poll() is None:
                    api(
                        self.base_url,
                        "POST",
                        f"/api/sessions/{self.session_id}/close",
                        {"reason": "e2e_finished"},
                    )
            except Exception:
                pass
            self.stop_chrome()
            self.stop_hub()
            self.site.stop()
            if not self.args.keep_temp:
                shutil.rmtree(self.workspace, ignore_errors=True)
        report = self.report("passed")
        print(f"E2E пройден. Отчёт: {report}")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Сквозная проверка браузерного ядра")
    parser.add_argument("--chrome", help="Путь к Google Chrome или Chromium")
    parser.add_argument("--output", help="Каталог артефактов")
    parser.add_argument("--headed", action="store_true", help="Запустить Chrome с окном")
    parser.add_argument("--keep-temp", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    return BrowserE2E(build_parser().parse_args(argv)).run()


if __name__ == "__main__":
    raise SystemExit(main())

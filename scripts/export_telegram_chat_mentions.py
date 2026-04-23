#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_BASE = REPO_ROOT / "artifacts" / "telegram_exports" / "latest_chat_mentions"
DEFAULT_ARCHIVE_DIR = REPO_ROOT / "artifacts" / "telegram_exports"


def _load_export_module():
    module_path = REPO_ROOT / "scripts" / "export_telegram_members_non_pii.py"
    spec = importlib.util.spec_from_file_location("telegram_export_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _append_unique_usernames(existing: list[str], candidates: list[str]) -> int:
    seen = {value.lower() for value in existing}
    added = 0
    for value in candidates:
        username = str(value or "").strip()
        if not username:
            continue
        if not username.startswith("@"):
            username = f"@{username.lstrip('@')}"
        key = username.lower()
        if key in seen:
            continue
        seen.add(key)
        existing.append(username)
        added += 1
    return added


def _archive_output_copy(
    *,
    archive_dir: Path,
    source_path: Path,
    group_url: str,
    label: str,
    count: int,
) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    export_mod = _load_export_module()
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    group_slug = export_mod._path_slug(export_mod._dialog_fragment_from_url(group_url) or group_url or "group", fallback="group")
    label_slug = export_mod._path_slug(label, fallback="mentions")
    archive_path = archive_dir / f"{timestamp}_{label_slug}_{group_slug}_{count}{source_path.suffix}"
    shutil.copyfile(source_path, archive_path)
    return archive_path


def _write_outputs(
    *,
    output_base: Path,
    usernames: list[str],
    group_url: str,
    steps_done: int,
    runtime_sec: float,
) -> dict[str, Path]:
    output_base.parent.mkdir(parents=True, exist_ok=True)
    txt_path = output_base.with_suffix(".txt")
    json_path = output_base.with_suffix(".json")

    txt_body = "\n".join(usernames)
    if usernames:
        txt_body += "\n"
    txt_path.write_text(txt_body, encoding="utf-8")

    payload = {
        "group_url": group_url,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(usernames),
        "scroll_steps_done": steps_done,
        "runtime_sec": round(runtime_sec, 2),
        "usernames": usernames,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "txt": txt_path,
        "json": json_path,
    }


def _append_index(
    *,
    archive_dir: Path,
    group_url: str,
    target_count: int,
    steps_done: int,
    runtime_sec: float,
    txt_path: Path,
    json_path: Path,
    archived_txt: Path,
    archived_json: Path,
    count: int,
) -> None:
    index_path = archive_dir / "INDEX.md"
    entry_lines = [
        f"## {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Группа: `{group_url}`",
        f"Режим: `chat-mentions`",
        f"Target usernames: **{target_count}**",
        f"Собрано usernames: **{count}**",
        f"Chat scroll steps: **{steps_done}**",
        f"Runtime: **{runtime_sec:.2f}s**",
        f"Usernames TXT: `{txt_path}`",
        f"Usernames JSON: `{json_path}`",
        f"Архив usernames TXT: `{archived_txt}`",
        f"Архив usernames JSON: `{archived_json}`",
        "",
    ]
    entry_text = "\n".join(entry_lines).rstrip() + "\n"
    if index_path.exists():
        previous = index_path.read_text(encoding="utf-8").rstrip()
        prefix = f"{previous}\n\n" if previous else ""
        index_path.write_text(prefix + entry_text, encoding="utf-8")
    else:
        index_path.write_text("# Telegram Export Index\n\n" + entry_text, encoding="utf-8")


def _collect_chat_mentions(
    *,
    export_mod,
    server: str,
    token: str,
    client_id: str,
    tab_id: int,
    group_url: str,
    timeout_sec: int,
    scroll_steps: int,
    target_count: int,
    max_runtime_sec: int,
    scroll_burst: int,
    no_growth_limit: int,
) -> tuple[list[str], dict[str, int | float]]:
    usernames: list[str] = []
    no_growth_steps = 0
    scroll_steps_done = 0
    started_at = time.time()

    read_step = 0
    while True:
        if time.time() - started_at >= max(max_runtime_sec, 5):
            print(f"WARN: chat mentions runtime limit reached ({max_runtime_sec}s), stopping")
            break

        body_html = export_mod._send_get_html(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            timeout_sec=max(timeout_sec, 5),
            selector="body",
        )
        found = [f"@{value}" for value in export_mod._extract_chat_mention_usernames(body_html)]
        added = _append_unique_usernames(usernames, found)
        print(f"INFO: mention step {read_step} -> total {len(usernames)} usernames (added {added})")
        read_step += 1

        if len(usernames) >= target_count:
            break
        if scroll_steps_done >= max(scroll_steps, 0):
            break

        if added <= 0:
            no_growth_steps += 1
        else:
            no_growth_steps = 0
        if no_growth_steps >= max(no_growth_limit, 1):
            print(f"INFO: mention export auto-stop after {max(no_growth_limit, 1)} no-growth steps")
            break

        burst_count = min(max(scroll_burst, 1), max(scroll_steps, 0) - scroll_steps_done)
        moved_in_burst = 0
        for _ in range(burst_count):
            if time.time() - started_at >= max(max_runtime_sec, 5):
                break
            if not export_mod._scroll_chat_up(
                server=server,
                token=token,
                client_id=client_id,
                tab_id=tab_id,
                timeout_sec=min(max(timeout_sec, 5), 10),
            ):
                break
            moved_in_burst += 1
            scroll_steps_done += 1
            time.sleep(export_mod.CHAT_SCROLL_SETTLE_SEC)
        if moved_in_burst <= 0:
            break

    return usernames, {
        "scroll_steps_done": scroll_steps_done,
        "runtime_sec": time.time() - started_at,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Быстрый экспорт @username, найденных в Telegram chat history/mentions."
    )
    parser.add_argument("--server", default="http://127.0.0.1:8765")
    parser.add_argument("--token", default="")
    parser.add_argument("--client-id", default="")
    parser.add_argument("--tab-id", type=int, default=None)
    parser.add_argument("--group-url", default="https://web.telegram.org/a/#-")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--scroll-steps", type=int, default=20)
    parser.add_argument(
        "--scroll-burst",
        type=int,
        default=1,
        help="Сколько шагов scroll делать между чтениями body HTML (default: 1)",
    )
    parser.add_argument(
        "--no-growth-limit",
        type=int,
        default=3,
        help="Сколько чтений подряд без новых usernames разрешено до auto-stop (default: 3)",
    )
    parser.add_argument("--target-count", type=int, default=40)
    parser.add_argument("--max-runtime", type=int, default=300)
    parser.add_argument(
        "--output-base",
        default=str(DEFAULT_OUTPUT_BASE),
        help=f"Базовый путь без расширения; будут созданы .txt и .json (default: {DEFAULT_OUTPUT_BASE})",
    )
    parser.add_argument(
        "--archive-dir",
        default=str(DEFAULT_ARCHIVE_DIR),
        help=f"Каталог для архивных копий и индекса (default: {DEFAULT_ARCHIVE_DIR})",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    export_mod = _load_export_module()
    token = args.token or export_mod.os.getenv(export_mod.TOKEN_ENV, "") or export_mod.DEFAULT_TOKEN
    server = export_mod._norm_server(args.server)

    try:
        clients_response = export_mod._http_json_retry(server, token, "GET", "/api/clients")
        clients = clients_response.get("clients") or []
        if not isinstance(clients, list):
            raise RuntimeError("Invalid clients payload from hub")

        client_id, tab_id = export_mod._find_tab(
            clients=clients,
            client_id=args.client_id or None,
            tab_id=args.tab_id,
            url_pattern=args.group_url,
        )
        if not export_mod._ensure_group_dialog_url(
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            group_url=args.group_url,
            timeout_sec=max(args.timeout, 5),
        ):
            raise RuntimeError("Не удалось открыть/подтвердить целевой Telegram-чат")

        usernames, stats = _collect_chat_mentions(
            export_mod=export_mod,
            server=server,
            token=token,
            client_id=client_id,
            tab_id=tab_id,
            group_url=args.group_url,
            timeout_sec=max(args.timeout, 5),
            scroll_steps=max(args.scroll_steps, 0),
            target_count=max(args.target_count, 1),
            max_runtime_sec=max(args.max_runtime, 5),
            scroll_burst=max(args.scroll_burst, 1),
            no_growth_limit=max(args.no_growth_limit, 1),
        )
        if not usernames:
            raise RuntimeError("Не удалось собрать ни одного @username из chat history")

        output_base = Path(args.output_base).expanduser()
        outputs = _write_outputs(
            output_base=output_base,
            usernames=usernames,
            group_url=args.group_url,
            steps_done=int(stats["scroll_steps_done"]),
            runtime_sec=float(stats["runtime_sec"]),
        )
        archive_dir = Path(args.archive_dir).expanduser()
        archived_txt = _archive_output_copy(
            archive_dir=archive_dir,
            source_path=outputs["txt"],
            group_url=args.group_url,
            label="chat-mentions-usernames",
            count=len(usernames),
        )
        archived_json = _archive_output_copy(
            archive_dir=archive_dir,
            source_path=outputs["json"],
            group_url=args.group_url,
            label="chat-mentions-meta",
            count=len(usernames),
        )
        _append_index(
            archive_dir=archive_dir,
            group_url=args.group_url,
            target_count=max(args.target_count, 1),
            steps_done=int(stats["scroll_steps_done"]),
            runtime_sec=float(stats["runtime_sec"]),
            txt_path=outputs["txt"],
            json_path=outputs["json"],
            archived_txt=archived_txt,
            archived_json=archived_json,
            count=len(usernames),
        )

        print(f"OK: saved {len(usernames)} chat usernames to {outputs['txt']}")
        print(f"OK: saved metadata to {outputs['json']}")
        print(f"OK: archived usernames txt saved to {archived_txt}")
        print(f"OK: archived usernames json saved to {archived_json}")
        if len(usernames) < max(args.target_count, 1):
            print(
                f"WARN: target {max(args.target_count, 1)} not reached, current count {len(usernames)}",
                file=sys.stderr,
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

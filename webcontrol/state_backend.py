from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .protocol import STORAGE_SCHEMA_VERSION
from .utils import dump_json, load_json, now_utc_iso


class StateBackendError(RuntimeError):
    pass


class SQLiteStateBackend:
    """Транзакционное хранилище состояния с диагностическим JSON-зеркалом."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.database_file = state_file.with_suffix(".sqlite3")
        self.backup_dir = state_file.parent / "backups"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.database_file,
            timeout=10,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._configure()
        self._migrate_schema()

    def _configure(self) -> None:
        cursor = self._connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    def _migrate_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS state_document (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    revision INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS journal (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    recorded_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    entity_id TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(STORAGE_SCHEMA_VERSION),),
            )

    def load(self, default: dict[str, Any]) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT payload FROM state_document WHERE singleton = 1"
        ).fetchone()
        if row:
            try:
                payload = json.loads(str(row["payload"]))
            except json.JSONDecodeError as exc:
                raise StateBackendError(f"SQLite contains invalid state JSON: {exc}") from exc
            if isinstance(payload, dict):
                return payload
            raise StateBackendError("SQLite state document must be a JSON object")

        legacy = load_json(self.state_file, default={})
        initial = legacy if isinstance(legacy, dict) and legacy else dict(default)
        if self.state_file.exists() and legacy:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            backup = self.backup_dir / f"{self.state_file.stem}-before-sqlite-{_timestamp()}.json"
            shutil.copy2(self.state_file, backup)
        self.save(initial, event_type="storage_initialized")
        return initial

    def save(
        self,
        state: dict[str, Any],
        *,
        event_type: str = "state_saved",
        entity_id: str | None = None,
        event_payload: dict[str, Any] | None = None,
    ) -> int:
        serialized = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        recorded_at = now_utc_iso()
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                "SELECT revision FROM state_document WHERE singleton = 1"
            ).fetchone()
            revision = int(row["revision"]) + 1 if row else 1
            self._connection.execute(
                """
                INSERT INTO state_document(singleton, revision, updated_at, payload)
                VALUES(1, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    revision = excluded.revision,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (revision, recorded_at, serialized),
            )
            self._connection.execute(
                """
                INSERT INTO journal(recorded_at, event_type, entity_id, payload)
                VALUES(?, ?, ?, ?)
                """,
                (
                    recorded_at,
                    event_type,
                    entity_id,
                    json.dumps(event_payload or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

        mirror = dict(state)
        mirror["storage"] = {
            "backend": "sqlite-wal",
            "database_file": str(self.database_file),
            "schema_version": STORAGE_SCHEMA_VERSION,
            "revision": revision,
            "updated_at": recorded_at,
            "authoritative": True,
        }
        dump_json(self.state_file, mirror)
        return revision

    def append_journal(
        self,
        event_type: str,
        *,
        entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO journal(recorded_at, event_type, entity_id, payload)
                VALUES(?, ?, ?, ?)
                """,
                (
                    now_utc_iso(),
                    event_type,
                    entity_id,
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                ),
            )

    def backup(self, destination: Path | None = None) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        target = (
            destination or self.backup_dir / f"{self.database_file.stem}-{_timestamp()}.sqlite3"
        )
        target = target.expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(target)
        try:
            self._connection.backup(connection)
        finally:
            connection.close()
        return target

    def journal_tail(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1000))
        rows = self._connection.execute(
            """
            SELECT sequence, recorded_at, event_type, entity_id, payload
            FROM journal
            ORDER BY sequence DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        result = []
        for row in reversed(rows):
            try:
                payload = json.loads(str(row["payload"]))
            except json.JSONDecodeError:
                payload = {"raw": str(row["payload"])}
            result.append(
                {
                    "sequence": int(row["sequence"]),
                    "recorded_at": str(row["recorded_at"]),
                    "event_type": str(row["event_type"]),
                    "entity_id": row["entity_id"],
                    "payload": payload,
                }
            )
        return result

    def close(self) -> None:
        self._connection.close()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

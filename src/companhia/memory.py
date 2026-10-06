from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def now() -> str:
    return datetime.now(UTC).isoformat()


def terms(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.casefold()) if len(w) > 3}


class Store:
    def __init__(self, path: Path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        # Antes de migrar, mantém uma cópia recuperável do banco, sem recriá-lo.
        needs_migration = self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='messages'"
        ).fetchone()
        if needs_migration and "AUTOINCREMENT" not in needs_migration[0].upper():
            backup_path = path.with_name(path.name + ".before-v2.bak")
            if not backup_path.exists():
                with sqlite3.connect(backup_path) as backup:
                    self.db.backup(backup)
        with self.transaction() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, turn TEXT, role TEXT, content TEXT,
                    state TEXT, created TEXT);
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT, kind TEXT, source TEXT,
                    created TEXT, updated TEXT, active INTEGER DEFAULT 1);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY, turn TEXT, modality TEXT, requested TEXT,
                    returned TEXT, state TEXT, usage TEXT, created TEXT, elapsed REAL);
                CREATE TABLE IF NOT EXISTS deleted_messages (id INTEGER PRIMARY KEY, deleted_at TEXT);
            """)
            self._migrate_ids(db)
            db.execute("UPDATE messages SET state='interrupted' WHERE state='pending'")
            db.execute("UPDATE calls SET state='interrupted' WHERE state='pending'")

    def _migrate_ids(self, db):
        # DDL e cópia transacionais. IDs e fontes existentes permanecem intactos.
        db.execute("BEGIN IMMEDIATE")
        for table in ("messages", "memories"):
            schema = db.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
            if "AUTOINCREMENT" not in schema.upper():
                new_schema = re.sub(
                    rf'^CREATE TABLE\s+(?:"{table}"|`{table}`|\[{table}\]|{table})',
                    f"CREATE TABLE {table}_v2",
                    schema,
                    count=1,
                    flags=re.I,
                )
                new_schema = re.sub(
                    r"INTEGER\s+PRIMARY\s+KEY",
                    "INTEGER PRIMARY KEY AUTOINCREMENT",
                    new_schema,
                    count=1,
                    flags=re.I,
                )
                db.execute(new_schema)
                db.execute(f"INSERT INTO {table}_v2 SELECT * FROM {table}")
                db.execute(f"DROP TABLE {table}")
                db.execute(f"ALTER TABLE {table}_v2 RENAME TO {table}")
        refs = [row[0] for row in db.execute("SELECT source FROM memories")]
        message_ids = [int(m[1]) for value in refs if (m := re.match(r"message:(\d+)", value or ""))]
        memory_ids = [int(m[1]) for value in refs if (m := re.match(r"ui:correction:(\d+)", value or ""))]
        for id in message_ids:
            if not db.execute("SELECT 1 FROM messages WHERE id=?", (id,)).fetchone():
                db.execute("INSERT OR IGNORE INTO deleted_messages VALUES(?,?)", (id, now()))
        barrier = db.execute("SELECT value FROM meta WHERE key='context_barrier'").fetchone()
        deleted_max = db.execute("SELECT COALESCE(MAX(id),0) FROM deleted_messages").fetchone()[0]
        for table, references in [
            ("messages", message_ids + [int(barrier[0]) if barrier else 0, deleted_max]),
            ("memories", memory_ids),
        ]:
            highest = max([db.execute(f"SELECT COALESCE(MAX(id),0) FROM {table}").fetchone()[0]] + references)
            row = db.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (table,)).fetchone()
            if row:
                db.execute("UPDATE sqlite_sequence SET seq=? WHERE name=?", (max(row[0], highest), table))
            else:
                db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)", (table, highest))
        db.execute("INSERT OR REPLACE INTO meta VALUES('schema_version','2')")

    def source_label(self, source: str) -> str:
        match = re.match(r"message:(\d+)", source)
        if match and not self.rows("SELECT id FROM messages WHERE id=?", (int(match[1]),)):
            return source + " (mensagem removida)"
        return source

    @contextmanager
    def transaction(self):
        with self.lock, self.db:
            yield self.db

    def rows(self, query: str, args=()) -> list[dict]:
        with self.lock:
            return [dict(row) for row in self.db.execute(query, args).fetchall()]

    def message(self, turn: str, role: str, content: str, state="complete") -> int:
        with self.transaction() as db:
            return db.execute(
                "INSERT INTO messages(turn,role,content,state,created) VALUES(?,?,?,?,?)",
                (turn, role, content, state, now()),
            ).lastrowid

    def update_message(self, id: int, content: str, state: str):
        with self.transaction() as db:
            db.execute("UPDATE messages SET content=?,state=? WHERE id=?", (content, state, id))

    def recent(self, limit=12, for_context=False) -> list[dict]:
        barrier = int(self.get_meta("context_barrier", "0")) if for_context else 0
        clause = "AND state='complete'" if for_context else ""
        return list(
            reversed(
                self.rows(
                    f"SELECT * FROM messages WHERE id>? {clause} ORDER BY id DESC LIMIT ?", (barrier, limit)
                )
            )
        )

    def get_meta(self, key: str, default="") -> str:
        rows = self.rows("SELECT value FROM meta WHERE key=?", (key,))
        return rows[0]["value"] if rows else default

    def set_meta(self, key: str, value: str):
        with self.transaction() as db:
            db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, value))

    def invalidate_context(self):
        with self.transaction() as db:
            latest = db.execute("SELECT COALESCE(MAX(id),0) FROM messages").fetchone()[0]
            db.execute("INSERT OR REPLACE INTO meta VALUES('context_barrier',?)", (str(latest),))
            db.execute("DELETE FROM meta WHERE key='summary'")

    def memories(self, include_inactive=False) -> list[dict]:
        return self.rows(
            "SELECT * FROM memories "
            + ("" if include_inactive else "WHERE active=1 ")
            + "ORDER BY updated DESC,id DESC"
        )

    def remember(self, content: str, source: str, kind="explicit", replace_id: int | None = None) -> int:
        content = content.strip()
        if not content or len(content) > 2000:
            raise ValueError("Memória deve ter entre 1 e 2000 caracteres.")
        with self.transaction() as db:
            if replace_id is not None:
                db.execute("UPDATE memories SET active=0,updated=? WHERE id=?", (now(), replace_id))
                self.invalidate_context()
            duplicate = db.execute(
                "SELECT id FROM memories WHERE active=1 AND content=?", (content,)
            ).fetchone()
            if duplicate:
                return duplicate[0]
            return db.execute(
                "INSERT INTO memories(content,kind,source,created,updated) VALUES(?,?,?,?,?)",
                (content, kind, source, now(), now()),
            ).lastrowid

    def forget(self, id: int):
        with self.transaction() as db:
            db.execute("DELETE FROM memories WHERE id=?", (id,))
            self.invalidate_context()

    def clear_history(self):
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO deleted_messages SELECT id,? FROM messages", (now(),))
            db.execute("DELETE FROM messages")
            db.execute("DELETE FROM meta WHERE key IN ('summary','context_barrier')")

    def relevant(self, text: str, limit=5) -> list[dict]:
        keywords = terms(text)
        return sorted(self.memories(), key=lambda m: len(keywords & terms(m["content"])), reverse=True)[
            :limit
        ]

    def memory_command(self, text: str, message_id: int) -> str | None:
        content = text.strip()
        match = re.fullmatch(r"(?:lembra|lembre|memoriza|memorize)(?:\s+que)?\s+(.+)", content, re.I | re.S)
        if match:
            id = self.remember(match[1], f"message:{message_id}")
            return f"Registrei a memória #{id}: {match[1]}"
        match = re.fullmatch(
            r"(?:corrige|corrija)\s+(?:a\s+)?mem[oó]ria\s+#?(\d+)\s*[:=]\s*(.+)", content, re.I | re.S
        )
        if match:
            id = int(match[1])
            if not self.rows("SELECT id FROM memories WHERE id=? AND active=1", (id,)):
                return "Não encontrei essa memória ativa. Consulte a aba Memórias."
            new_id = self.remember(match[2], f"message:{message_id}", replace_id=id)
            return f"Corrigi a memória #{id}. A versão ativa agora é #{new_id}: {match[2]}"
        match = re.fullmatch(r"(?:esquece|esqueça|esqueca)\s+(.+)", content, re.I | re.S)
        if match:
            query = re.sub(r"^(?:a\s+)?mem[oó]ria\s+", "", match[1], flags=re.I).strip()
            matches = [
                m
                for m in self.memories()
                if str(m["id"]) == query.lstrip("#") or query.casefold() in m["content"].casefold()
            ]
            if len(matches) != 1:
                return "Não encontrei uma memória única. Use 'esquece memória #ID' ou a aba Memórias."
            self.forget(matches[0]["id"])
            return "Apaguei essa memória e retirei o contexto anterior das próximas chamadas."
        return None

    def start_call(self, turn: str, modality: str, model: str, max_calls: int, max_tokens: int) -> int:
        with self.transaction() as db:
            rows = db.execute(
                "SELECT usage FROM calls WHERE created>=? AND requested NOT LIKE 'mock/%' "
                "AND requested NOT LIKE 'windows/%'",
                (now()[:10],),
            ).fetchall()
            tokens = sum(json.loads(r[0] or "{}").get("total_tokens", 0) or 0 for r in rows)
            if not model.startswith(("mock/", "windows/")) and (
                len(rows) >= max_calls or tokens >= max_tokens
            ):
                raise ValueError("Limite diário de chamadas ou tokens atingido. Ajuste nas configurações.")
            return db.execute(
                "INSERT INTO calls(turn,modality,requested,state,created) VALUES(?,?,?,?,?)",
                (turn, modality, model, "pending", now()),
            ).lastrowid

    def finish_call(self, id: int, state: str, returned: str, usage: dict, elapsed: float):
        with self.transaction() as db:
            db.execute(
                "UPDATE calls SET state=?,returned=?,usage=?,elapsed=? WHERE id=?",
                (state, returned, json.dumps(usage), elapsed, id),
            )

    def close(self):
        with self.lock:
            self.db.close()

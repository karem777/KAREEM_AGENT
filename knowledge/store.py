from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable


class KnowledgeStore:
    """Local, dependency-light knowledge store with SQLite FTS5.

    It is intentionally usable without external vector DBs. Mem0/Qdrant are added
    separately as an optional long-term semantic layer.
    """

    def __init__(self, root: str | Path = "data/knowledge") -> None:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "knowledge.sqlite3"
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE,
                title TEXT,
                domain TEXT,
                fetched_at REAL,
                content_hash TEXT,
                metadata_json TEXT
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                source_id INTEGER,
                chunk_index INTEGER,
                text TEXT,
                FOREIGN KEY(source_id) REFERENCES sources(id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                text,
                content='chunks',
                content_rowid='id'
            );
            CREATE TABLE IF NOT EXISTS skills (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                description TEXT,
                body TEXT,
                created_at REAL,
                metadata_json TEXT
            );
            """
        )
        self.conn.commit()

    def add_document(
        self,
        url: str,
        title: str,
        text: str,
        domain: str = "",
        metadata: dict[str, Any] | None = None,
        chunk_size: int = 1800,
    ) -> int:
        clean = " ".join(str(text or "").split()).strip()
        if not clean:
            raise ValueError("Cannot store empty knowledge document")
        digest = hashlib.sha256(clean.encode("utf-8", "ignore")).hexdigest()
        now = time.time()
        self.conn.execute(
            """
            INSERT INTO sources(url,title,domain,fetched_at,content_hash,metadata_json)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET
                title=excluded.title,
                domain=excluded.domain,
                fetched_at=excluded.fetched_at,
                content_hash=excluded.content_hash,
                metadata_json=excluded.metadata_json
            """,
            (url, title, domain, now, digest, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        source_id = self.conn.execute("SELECT id FROM sources WHERE url=?", (url,)).fetchone()[0]
        self.conn.execute("DELETE FROM chunks WHERE source_id=?", (source_id,))
        chunks = [clean[i:i + chunk_size] for i in range(0, len(clean), chunk_size)]
        for idx, chunk in enumerate(chunks):
            cur = self.conn.execute(
                "INSERT INTO chunks(source_id,chunk_index,text) VALUES(?,?,?)",
                (source_id, idx, chunk),
            )
            row_id = cur.lastrowid
            self.conn.execute("INSERT INTO chunks_fts(rowid,text) VALUES(?,?)", (row_id, chunk))
        self.conn.commit()
        return int(source_id)

    def search(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        q = " ".join(str(query or "").split()).strip()
        if not q:
            return []
        try:
            rows = self.conn.execute(
                """
                SELECT c.id, c.text, s.url, s.title, s.domain
                FROM chunks_fts f
                JOIN chunks c ON c.id=f.rowid
                JOIN sources s ON s.id=c.source_id
                WHERE chunks_fts MATCH ?
                LIMIT ?
                """,
                (q, int(limit)),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = self.conn.execute(
                """
                SELECT c.id, c.text, s.url, s.title, s.domain
                FROM chunks c JOIN sources s ON s.id=c.source_id
                WHERE c.text LIKE ?
                ORDER BY c.id DESC LIMIT ?
                """,
                (f"%{q}%", int(limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_sources(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT url,title,domain,fetched_at FROM sources ORDER BY fetched_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_skill(self, name: str, description: str, body: str, metadata: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO skills(name,description,body,created_at,metadata_json)
            VALUES(?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                description=excluded.description,
                body=excluded.body,
                created_at=excluded.created_at,
                metadata_json=excluded.metadata_json
            """,
            (name, description, body, time.time(), json.dumps(metadata or {}, ensure_ascii=False)),
        )
        self.conn.commit()

    def list_skills(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT name,description,body,created_at,metadata_json FROM skills ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

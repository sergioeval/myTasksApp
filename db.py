"""PostgreSQL persistence (Supabase) for task tracker."""
from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from typing import Any

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor


def _postgres_config() -> dict[str, Any]:
    """Load connection settings from Streamlit secrets or environment."""
    try:
        import streamlit as st

        if hasattr(st, "secrets") and "postgres" in st.secrets:
            sec = st.secrets["postgres"]
            return {
                "host": str(sec["host"]).strip(),
                "port": int(sec.get("port", 5432)),
                "database": str(sec.get("database", "postgres")).strip(),
                "user": str(sec["user"]).strip(),
                "password": str(sec["password"]),
                "sslmode": str(sec.get("sslmode", "require")).strip(),
            }
    except Exception:
        pass

    load_dotenv()
    host = os.environ.get("POSTGRES_HOST", "").strip()
    if not host:
        raise RuntimeError(
            "PostgreSQL is not configured. Add a [postgres] section to "
            ".streamlit/secrets.toml (see secrets.toml.example) or set POSTGRES_* env vars."
        )
    return {
        "host": host,
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "database": os.environ.get("POSTGRES_DATABASE", "postgres").strip(),
        "user": os.environ.get("POSTGRES_USER", "").strip(),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "sslmode": os.environ.get("POSTGRES_SSLMODE", "require").strip(),
    }


def _connect():
    """Open a psycopg2 connection.

    Supabase direct hostnames often resolve to IPv6 first; many networks have no
    working IPv6 route ("Network is unreachable"). If an IPv4 address exists,
    we connect via ``hostaddr`` but keep ``host`` for TLS server name validation.
    """
    cfg = _postgres_config()
    host = cfg["host"]
    port = cfg["port"]
    kw = dict(
        host=host,
        port=port,
        dbname=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        sslmode=cfg["sslmode"],
        cursor_factory=RealDictCursor,
    )
    try:
        infos = socket.getaddrinfo(
            host, port, socket.AF_INET, socket.SOCK_STREAM
        )
    except socket.gaierror:
        infos = []
    if infos:
        hostaddr = infos[0][4][0]
        kw["hostaddr"] = hostaddr
    return psycopg2.connect(**kw)


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS statuses (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    status_id INTEGER NOT NULL REFERENCES statuses(id),
                    due_date TEXT,
                    priority INTEGER NOT NULL DEFAULT 5,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS comments (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    body TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS task_checklist_items (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    body TEXT NOT NULL,
                    is_done BOOLEAN NOT NULL DEFAULT FALSE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS general_notes (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'Untitled',
                    body TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS tags (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS note_tags (
                    note_id INTEGER NOT NULL REFERENCES general_notes(id) ON DELETE CASCADE,
                    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                    PRIMARY KEY (note_id, tag_id)
                );
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS tags_name_lower
                ON tags (LOWER(name));
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status_id);
                CREATE INDEX IF NOT EXISTS idx_comments_task ON comments(task_id);
                CREATE INDEX IF NOT EXISTS idx_checklist_task ON task_checklist_items(task_id);
                CREATE INDEX IF NOT EXISTS idx_general_notes_created ON general_notes(created_at);
                CREATE INDEX IF NOT EXISTS idx_note_tags_tag ON note_tags(tag_id);
                CREATE INDEX IF NOT EXISTS idx_note_tags_note ON note_tags(note_id);
                """
            )
            cur.execute("SELECT COUNT(*) AS n FROM statuses")
            if cur.fetchone()["n"] == 0:
                cur.executemany(
                    "INSERT INTO statuses (name, sort_order) VALUES (%s, %s)",
                    [("To do", 0), ("In progress", 1), ("Done", 2)],
                )


# --- Statuses ---


def list_statuses():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, sort_order, created_at FROM statuses
                ORDER BY sort_order, id
                """
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]


def add_status(name: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO statuses (name, sort_order)
                SELECT %s, COALESCE(MAX(sort_order), -1) + 1 FROM statuses
                RETURNING id
                """,
                (name.strip(),),
            )
            return int(cur.fetchone()["id"])


def update_status_name(status_id: int, name: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE statuses SET name = %s WHERE id = %s",
                (name.strip(), status_id),
            )


def delete_status(status_id: int) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM tasks WHERE status_id = %s",
                (status_id,),
            )
            if cur.fetchone()["n"] > 0:
                return False
            cur.execute("DELETE FROM statuses WHERE id = %s", (status_id,))
        return True


def status_options():
    return [(s["id"], s["name"]) for s in list_statuses()]


# --- Tasks ---


def list_tasks():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, t.title, t.description, t.status_id, t.due_date, t.priority,
                       t.created_at, t.updated_at, s.name AS status_name
                FROM tasks t
                JOIN statuses s ON s.id = t.status_id
                ORDER BY t.priority ASC, t.updated_at DESC, t.id DESC
                """
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]


def get_task(task_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, t.title, t.description, t.status_id, t.due_date, t.priority,
                       t.created_at, t.updated_at, s.name AS status_name
                FROM tasks t
                JOIN statuses s ON s.id = t.status_id
                WHERE t.id = %s
                """,
                (task_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None


def create_task(
    title: str,
    description: str | None,
    status_id: int,
    due_date: str | None = None,
    priority: int = 5,
) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tasks (title, description, status_id, due_date, priority)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    title.strip(),
                    (description or "").strip() or None,
                    status_id,
                    due_date.strip() if due_date and due_date.strip() else None,
                    int(priority),
                ),
            )
            return int(cur.fetchone()["id"])


def set_task_status(task_id: int, status_id: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tasks SET status_id = %s, updated_at = NOW() WHERE id = %s",
                (status_id, task_id),
            )


def update_task_meta(
    task_id: int,
    title: str,
    description: str | None,
    due_date: str | None = None,
    priority: int = 5,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tasks
                SET title = %s, description = %s, due_date = %s, priority = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    title.strip(),
                    (description or "").strip() or None,
                    due_date.strip() if due_date and due_date.strip() else None,
                    int(priority),
                    task_id,
                ),
            )


def delete_task(task_id: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))


# --- Comments ---


def list_comments(task_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, body, created_at FROM comments
                WHERE task_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (task_id,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]


def add_comment(task_id: int, body: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO comments (task_id, body) VALUES (%s, %s)
                RETURNING id
                """,
                (task_id, body.strip()),
            )
            return int(cur.fetchone()["id"])


# --- Task checklist items ---


def list_checklist_items(task_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, task_id, body, is_done, sort_order, created_at
                FROM task_checklist_items
                WHERE task_id = %s
                ORDER BY is_done ASC, sort_order ASC, id ASC
                """,
                (task_id,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]


def add_checklist_item(task_id: int, body: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO task_checklist_items (task_id, body, sort_order)
                SELECT %s, %s, COALESCE(MAX(sort_order), -1) + 1
                FROM task_checklist_items
                WHERE task_id = %s
                RETURNING id
                """,
                (task_id, body.strip(), task_id),
            )
            return int(cur.fetchone()["id"])


def set_checklist_item_done(item_id: int, is_done: bool) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE task_checklist_items SET is_done = %s WHERE id = %s",
                (is_done, item_id),
            )


def delete_checklist_item(item_id: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM task_checklist_items WHERE id = %s", (item_id,))


# --- Tags (for general notes) ---


def list_tags():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, created_at FROM tags
                ORDER BY LOWER(name)
                """
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]


def add_tag(name: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tags (name) VALUES (%s) RETURNING id",
                (name.strip(),),
            )
            return int(cur.fetchone()["id"])


def delete_tag(tag_id: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM note_tags WHERE tag_id = %s", (tag_id,))
            cur.execute("DELETE FROM tags WHERE id = %s", (tag_id,))


# --- General notes (not tied to tasks) ---


def list_general_notes(filter_tag_id: int | None = None):
    """Newest note first. Each dict includes ``tags``: list of {id, name}."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            if filter_tag_id is None:
                cur.execute(
                    """
                    SELECT id, title, body, created_at FROM general_notes
                    ORDER BY created_at DESC, id DESC
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT DISTINCT n.id, n.title, n.body, n.created_at
                    FROM general_notes n
                    JOIN note_tags nt ON nt.note_id = n.id AND nt.tag_id = %s
                    ORDER BY n.created_at DESC, n.id DESC
                    """,
                    (int(filter_tag_id),),
                )
            rows = cur.fetchall()
        notes = [dict(r) for r in rows]
        if not notes:
            return notes
        ids = [n["id"] for n in notes]
        ph = ",".join(["%s"] * len(ids))
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT nt.note_id, t.id AS tag_id, t.name AS tag_name
                FROM note_tags nt
                JOIN tags t ON t.id = nt.tag_id
                WHERE nt.note_id IN ({ph})
                ORDER BY LOWER(t.name)
                """,
                ids,
            )
            trows = cur.fetchall()
        by_note: dict[int, list[dict]] = {}
        for r in trows:
            by_note.setdefault(r["note_id"], []).append(
                {"id": r["tag_id"], "name": r["tag_name"]}
            )
        for n in notes:
            n["tags"] = by_note.get(n["id"], [])
        return notes


def get_general_note(note_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, body, created_at FROM general_notes WHERE id = %s",
                (note_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None


def add_general_note(title: str, body: str, tag_ids: list[int] | None = None) -> int:
    tag_ids = tag_ids or []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO general_notes (title, body) VALUES (%s, %s) RETURNING id",
                ((title or "").strip() or "Untitled", body.strip()),
            )
            nid = int(cur.fetchone()["id"])
            for tid in tag_ids:
                cur.execute(
                    "INSERT INTO note_tags (note_id, tag_id) VALUES (%s, %s)",
                    (nid, int(tid)),
                )
        return nid


def update_general_note(note_id: int, title: str, body: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE general_notes SET title = %s, body = %s WHERE id = %s",
                ((title or "").strip() or "Untitled", (body or "").strip(), note_id),
            )


def set_note_tags(note_id: int, tag_ids: list[int]) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM note_tags WHERE note_id = %s", (note_id,))
            for tid in tag_ids:
                cur.execute(
                    "INSERT INTO note_tags (note_id, tag_id) VALUES (%s, %s)",
                    (note_id, int(tid)),
                )


def delete_general_note(note_id: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM general_notes WHERE id = %s", (note_id,))

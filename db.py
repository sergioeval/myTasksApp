"""SQLite persistence for task tracker."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "tasks.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS statuses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status_id INTEGER NOT NULL REFERENCES statuses(id),
                due_date TEXT,
                priority INTEGER NOT NULL DEFAULT 5,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS task_checklist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                body TEXT NOT NULL,
                is_done INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS general_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS note_tags (
                note_id INTEGER NOT NULL REFERENCES general_notes(id) ON DELETE CASCADE,
                tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (note_id, tag_id)
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status_id);
            CREATE INDEX IF NOT EXISTS idx_comments_task ON comments(task_id);
            CREATE INDEX IF NOT EXISTS idx_checklist_task ON task_checklist_items(task_id);
            CREATE INDEX IF NOT EXISTS idx_general_notes_created ON general_notes(created_at);
            CREATE INDEX IF NOT EXISTS idx_note_tags_tag ON note_tags(tag_id);
            CREATE INDEX IF NOT EXISTS idx_note_tags_note ON note_tags(note_id);
            """
        )
        cur = conn.execute("SELECT COUNT(*) FROM statuses")
        if cur.fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO statuses (name, sort_order) VALUES (?, ?)",
                [("To do", 0), ("In progress", 1), ("Done", 2)],
            )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "due_date" not in cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT")
        if "priority" not in cols:
            conn.execute(
                "ALTER TABLE tasks ADD COLUMN priority INTEGER NOT NULL DEFAULT 5"
            )


# --- Statuses ---


def list_statuses():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, sort_order, created_at FROM statuses ORDER BY sort_order, id"
        ).fetchall()
        return [dict(r) for r in rows]


def add_status(name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO statuses (name, sort_order)
            SELECT ?, COALESCE(MAX(sort_order), -1) + 1 FROM statuses
            """,
            (name.strip(),),
        )
        return int(cur.lastrowid)


def update_status_name(status_id: int, name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE statuses SET name = ? WHERE id = ?",
            (name.strip(), status_id),
        )


def delete_status(status_id: int) -> bool:
    with get_conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status_id = ?", (status_id,)
        ).fetchone()[0]
        if n > 0:
            return False
        conn.execute("DELETE FROM statuses WHERE id = ?", (status_id,))
        return True


def status_options():
    return [(s["id"], s["name"]) for s in list_statuses()]


# --- Tasks ---


def list_tasks():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT t.id, t.title, t.description, t.status_id, t.due_date, t.priority,
                   t.created_at, t.updated_at, s.name AS status_name
            FROM tasks t
            JOIN statuses s ON s.id = t.status_id
            ORDER BY t.priority ASC, t.updated_at DESC, t.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_task(task_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT t.id, t.title, t.description, t.status_id, t.due_date, t.priority,
                   t.created_at, t.updated_at, s.name AS status_name
            FROM tasks t
            JOIN statuses s ON s.id = t.status_id
            WHERE t.id = ?
            """,
            (task_id,),
        ).fetchone()
        return dict(row) if row else None


def create_task(
    title: str,
    description: str | None,
    status_id: int,
    due_date: str | None = None,
    priority: int = 5,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (title, description, status_id, due_date, priority)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                title.strip(),
                (description or "").strip() or None,
                status_id,
                due_date.strip() if due_date and due_date.strip() else None,
                int(priority),
            ),
        )
        return int(cur.lastrowid)


def set_task_status(task_id: int, status_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET status_id = ?, updated_at = datetime('now') WHERE id = ?",
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
        conn.execute(
            """
            UPDATE tasks
            SET title = ?, description = ?, due_date = ?, priority = ?,
                updated_at = datetime('now')
            WHERE id = ?
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
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


# --- Comments ---


def list_comments(task_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, body, created_at FROM comments
            WHERE task_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_comment(task_id: int, body: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO comments (task_id, body) VALUES (?, ?)",
            (task_id, body.strip()),
        )
        return int(cur.lastrowid)


# --- Task checklist items ---


def list_checklist_items(task_id: int):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, task_id, body, is_done, sort_order, created_at
            FROM task_checklist_items
            WHERE task_id = ?
            ORDER BY is_done ASC, sort_order ASC, id ASC
            """,
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def add_checklist_item(task_id: int, body: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO task_checklist_items (task_id, body, sort_order)
            SELECT ?, ?, COALESCE(MAX(sort_order), -1) + 1
            FROM task_checklist_items
            WHERE task_id = ?
            """,
            (task_id, body.strip(), task_id),
        )
        return int(cur.lastrowid)


def set_checklist_item_done(item_id: int, is_done: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE task_checklist_items SET is_done = ? WHERE id = ?",
            (1 if is_done else 0, item_id),
        )


def delete_checklist_item(item_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM task_checklist_items WHERE id = ?", (item_id,))


# --- Tags (for general notes) ---


def list_tags():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, created_at FROM tags
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]


def add_tag(name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tags (name) VALUES (?)",
            (name.strip(),),
        )
        return int(cur.lastrowid)


def delete_tag(tag_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM note_tags WHERE tag_id = ?", (tag_id,))
        conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))


# --- General notes (not tied to tasks) ---


def list_general_notes(filter_tag_id: int | None = None):
    """Newest note first. Each dict includes ``tags``: list of {id, name}."""
    with get_conn() as conn:
        if filter_tag_id is None:
            rows = conn.execute(
                """
                SELECT id, body, created_at FROM general_notes
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT DISTINCT n.id, n.body, n.created_at
                FROM general_notes n
                JOIN note_tags nt ON nt.note_id = n.id AND nt.tag_id = ?
                ORDER BY n.created_at DESC, n.id DESC
                """,
                (int(filter_tag_id),),
            ).fetchall()
        notes = [dict(r) for r in rows]
        if not notes:
            return notes
        ids = [n["id"] for n in notes]
        ph = ",".join("?" * len(ids))
        trows = conn.execute(
            f"""
            SELECT nt.note_id, t.id AS tag_id, t.name AS tag_name
            FROM note_tags nt
            JOIN tags t ON t.id = nt.tag_id
            WHERE nt.note_id IN ({ph})
            ORDER BY t.name COLLATE NOCASE
            """,
            ids,
        ).fetchall()
        by_note: dict[int, list[dict]] = {}
        for r in trows:
            by_note.setdefault(r["note_id"], []).append(
                {"id": r["tag_id"], "name": r["tag_name"]}
            )
        for n in notes:
            n["tags"] = by_note.get(n["id"], [])
        return notes


def add_general_note(body: str, tag_ids: list[int] | None = None) -> int:
    tag_ids = tag_ids or []
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO general_notes (body) VALUES (?)",
            (body.strip(),),
        )
        nid = int(cur.lastrowid)
        for tid in tag_ids:
            conn.execute(
                "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                (nid, int(tid)),
            )
        return nid


def set_note_tags(note_id: int, tag_ids: list[int]) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
        for tid in tag_ids:
            conn.execute(
                "INSERT INTO note_tags (note_id, tag_id) VALUES (?, ?)",
                (note_id, int(tid)),
            )


def delete_general_note(note_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM general_notes WHERE id = ?", (note_id,))

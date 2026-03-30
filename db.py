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

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status_id);
            CREATE INDEX IF NOT EXISTS idx_comments_task ON comments(task_id);
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

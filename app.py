"""
Task tracker: task list on the main view; details in a large modal dialog.
"""
import html
import sqlite3
from datetime import date, datetime
import streamlit as st

import db

st.set_page_config(page_title="My tasks", layout="wide", initial_sidebar_state="expanded")


def init():
    db.init_db()
    if "dialog_task_id" not in st.session_state:
        st.session_state.dialog_task_id = None


def fmt_ts(iso: str | None) -> str:
    if not iso:
        return "—"
    return iso.replace("T", " ").replace("Z", " UTC")


def parse_iso_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fmt_due(s: str | None) -> str:
    if not s:
        return "—"
    d = parse_iso_date(s)
    if d:
        return d.strftime("%b %d, %Y")
    return s


def fmt_days_until_due(s: str | None) -> str:
    d = parse_iso_date(s)
    if d is None:
        return "—"
    today = date.today()
    delta = (d - today).days
    if delta > 1:
        return f"{delta} days left"
    if delta == 1:
        return "1 day left"
    if delta == 0:
        return "Due today"
    if delta == -1:
        return "1 day overdue"
    return f"{-delta} days overdue"


def truncate_for_list(text: str | None, max_len: int = 100) -> str:
    if not text or not str(text).strip():
        return "—"
    t = " ".join(str(text).split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _task_table_hdr(label: str) -> None:
    st.markdown(
        f'<p style="margin:0 0 0.15rem 0;font-size:0.85rem;line-height:1.35;font-weight:600;">'
        f"{html.escape(label)}</p>",
        unsafe_allow_html=True,
    )


def _task_table_cell(text: str) -> None:
    st.markdown(
        f'<p style="margin:0;font-size:0.9rem;line-height:1.4;">'
        f"{html.escape(text or '—')}</p>",
        unsafe_allow_html=True,
    )


def sync_open_task_from_query_params() -> None:
    if "open_task" not in st.query_params:
        return
    raw = st.query_params["open_task"]
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    if raw is None:
        try:
            del st.query_params["open_task"]
        except KeyError:
            pass
        return
    try:
        tid = int(raw)
    except (TypeError, ValueError):
        try:
            del st.query_params["open_task"]
        except KeyError:
            pass
        return
    if db.get_task(tid):
        st.session_state.open_dialog_for_task = tid
    try:
        del st.query_params["open_task"]
    except KeyError:
        pass


def on_dialog_dismiss():
    st.session_state.dialog_task_id = None


@st.dialog("Task details", width="large", on_dismiss=on_dialog_dismiss)
def task_detail_modal(task_id: int):
    task = db.get_task(task_id)
    if not task:
        st.error("This task no longer exists.")
        if st.button("Close", key="dlg_close_missing"):
            st.session_state.dialog_task_id = None
            st.rerun()
        return

    st.markdown(f"## {html.escape(task['title'])}")
    due_disp = fmt_due(task.get("due_date"))
    pri = int(task.get("priority", 5))
    st.caption(
        f"ID `{task['id']}` · Priority **{pri}** (lower = higher) · "
        f"Created: {fmt_ts(task.get('created_at'))} · Due: **{due_disp}**"
    )

    opts = db.status_options()
    if not opts:
        st.warning("No statuses are configured.")
    else:
        status_labels = {sid: name for sid, name in opts}
        ids_list = [x[0] for x in opts]
        sidx = ids_list.index(task["status_id"]) if task["status_id"] in ids_list else 0
        new_status = st.selectbox(
            "Status",
            options=ids_list,
            index=sidx,
            format_func=lambda i: status_labels[i],
            key=f"dlg_status_{task_id}",
        )
        if new_status != task["status_id"]:
            db.set_task_status(task["id"], new_status)
            st.rerun()

    # Checkbox must live *outside* the form: widgets inside st.form do not rerun the script
    # until submit, so disabled=not use_due on the date picker never updated when toggling.
    use_due = st.checkbox(
        "Set a due date",
        value=bool(task.get("due_date")),
        key=f"dlg_use_due_{task_id}",
    )
    due_default = parse_iso_date(task.get("due_date")) or date.today()

    with st.form(f"dlg_edit_{task_id}"):
        et = st.text_input("Title", value=task["title"], max_chars=500)
        ed = st.text_area(
            "Description",
            value=task["description"] or "",
            height=140,
        )
        pr_edit = st.number_input(
            "Priority (integer, lower = listed first)",
            value=int(task.get("priority", 5)),
            step=1,
            min_value=0,
            key=f"dlg_pri_{task_id}",
        )
        due_edit = st.date_input(
            "Due date",
            value=due_default,
            disabled=not use_due,
            key=f"dlg_due_{task_id}",
        )
        if st.form_submit_button("Save changes"):
            due_str = due_edit.isoformat() if use_due else None
            db.update_task_meta(task["id"], et, ed, due_str, priority=int(pr_edit))
            st.rerun()

    st.divider()
    st.markdown("**Comments**")
    comments = db.list_comments(task["id"])
    if not comments:
        st.caption("No comments yet.")
    else:
        for c in comments:
            safe = html.escape(c["body"] or "").replace("\n", "<br/>")
            st.markdown(
                f'<div style="background:#eef1f6;padding:0.85rem;border-radius:8px;margin-bottom:0.5rem;'
                f'border:1px solid #d8dee8;color:#111827;font-size:1rem;line-height:1.5;">'
                f'<small style="color:#374151;font-weight:600;">{html.escape(fmt_ts(c["created_at"]))}</small><br/>'
                f'<span style="color:#0f172a;display:block;margin-top:0.35rem;">{safe}</span></div>',
                unsafe_allow_html=True,
            )

    with st.form(f"dlg_comment_{task_id}", clear_on_submit=True):
        body = st.text_area(
            "Add a comment",
            height=100,
            placeholder="Write a comment…",
        )
        if st.form_submit_button("Post comment"):
            if body and body.strip():
                db.add_comment(task["id"], body)
                st.rerun()
            else:
                st.warning("Enter some text before posting.")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Close", use_container_width=True, key=f"dlg_close_{task_id}"):
            st.session_state.dialog_task_id = None
            st.rerun()
    with c2:
        if st.button("Delete task", type="secondary", use_container_width=True, key=f"dlg_del_{task_id}"):
            db.delete_task(task["id"])
            st.session_state.dialog_task_id = None
            st.rerun()


init()
sync_open_task_from_query_params()

st.title("Task tracker")

tab_tasks, tab_statuses = st.tabs(["Tasks", "Statuses"])

# --- Sidebar: new task ---
with st.sidebar:
    st.header("New task")
    opts = db.status_options()
    if not opts:
        st.warning("Add at least one status under the **Statuses** tab.")
    else:
        with st.form("new_task", clear_on_submit=True):
            title = st.text_input("Title", max_chars=500)
            description = st.text_area("Description (optional)", height=100)
            status_labels = {sid: name for sid, name in opts}
            status_id = st.selectbox(
                "Initial status",
                options=[x[0] for x in opts],
                format_func=lambda i: status_labels[i],
            )
            due_new = st.date_input(
                "Due date (optional)",
                value=None,
            )
            priority_new = st.number_input(
                "Priority (lower = listed first)",
                value=5,
                step=1,
                min_value=0,
                help="Tasks are sorted by this value ascending (0 before 5 before 10).",
            )
            submitted = st.form_submit_button("Create task")
            if submitted:
                if not title or not title.strip():
                    st.error("Title is required.")
                else:
                    due_str = due_new.isoformat() if due_new else None
                    tid = db.create_task(
                        title,
                        description,
                        status_id,
                        due_str,
                        priority=int(priority_new),
                    )
                    st.session_state.open_dialog_for_task = tid
                    st.rerun()

# --- Tab Tasks ---
with tab_tasks:
    tasks = db.list_tasks()
    if not tasks:
        st.info("No tasks yet. Create one from the sidebar.")
    else:
        st.subheader("Task list")
        st.caption(
            "Tasks are sorted by **priority** (lower number first), then by last update. "
            "Click a **title** for details. **Due in** uses today’s local date. "
            "Descriptions are shortened here; open a task for the full text."
        )

        # Tertiary title buttons (LinkColumn opens in a new tab in Streamlit).
        st.markdown(
            """
<style>
div.st-key-task_list_table hr {
    margin: 0.45rem 0 !important;
}
div.st-key-task_list_table .stButton > button {
    min-height: 2.1rem !important;
    padding-top: 0.3rem !important;
    padding-bottom: 0.3rem !important;
    font-size: 0.9rem !important;
}
</style>
""",
            unsafe_allow_html=True,
        )
        col_weights = [0.98, 2.05, 3.05, 1.05, 1.05, 1.27]
        with st.container(border=True, key="task_list_table", gap="xsmall"):
            hdr = st.columns(col_weights, gap="small")
            for i, lab in enumerate(
                ("Priority", "Title", "Description", "Status", "Due", "Due in")
            ):
                with hdr[i]:
                    _task_table_hdr(lab)

            st.divider()

            for idx, t in enumerate(tasks):
                row = st.columns(col_weights, gap="small", vertical_alignment="center")
                with row[0]:
                    _task_table_cell(str(int(t.get("priority", 5))))
                with row[1]:
                    ttl = (t["title"] or "").strip() or "—"
                    btn_lbl = ttl if len(ttl) <= 54 else ttl[:51] + "…"
                    if st.button(
                        btn_lbl,
                        type="tertiary",
                        key=f"task_open_{t['id']}",
                        help=ttl if btn_lbl != ttl else None,
                        use_container_width=True,
                    ):
                        st.session_state.open_dialog_for_task = t["id"]
                        st.rerun()
                with row[2]:
                    _task_table_cell(truncate_for_list(t.get("description"), max_len=88))
                with row[3]:
                    _task_table_cell(t["status_name"])
                with row[4]:
                    _task_table_cell(fmt_due(t.get("due_date")))
                with row[5]:
                    _task_table_cell(fmt_days_until_due(t.get("due_date")))
                if idx < len(tasks) - 1:
                    st.divider()

        forced_tid = st.session_state.pop("open_dialog_for_task", None)
        if forced_tid is not None and db.get_task(forced_tid):
            st.session_state.dialog_task_id = forced_tid

        dlg_id = st.session_state.dialog_task_id
        if dlg_id is not None:
            if db.get_task(dlg_id):
                task_detail_modal(dlg_id)
            else:
                st.session_state.dialog_task_id = None

# --- Tab Statuses ---
with tab_statuses:
    st.subheader("Statuses")
    st.caption(
        "Statuses are used when you create tasks and when you change status in the task details. "
        "You cannot delete a status while any task is using it."
    )

    statuses = db.list_statuses()
    for s in statuses:
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            new_name = st.text_input(
                "Name",
                value=s["name"],
                key=f"sn_{s['id']}",
                label_visibility="collapsed",
            )
        with c2:
            if st.button("Save", key=f"save_s_{s['id']}"):
                if new_name.strip():
                    db.update_status_name(s["id"], new_name)
                    st.rerun()
        with c3:
            if st.button("Delete", key=f"del_s_{s['id']}"):
                if db.delete_status(s["id"]):
                    st.rerun()
                else:
                    st.error("Some tasks still use this status. Reassign them before deleting.")

    with st.form("add_status"):
        st.markdown("**Add status**")
        name = st.text_input("New status name")
        if st.form_submit_button("Add"):
            if name.strip():
                try:
                    db.add_status(name)
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That name already exists.")
            else:
                st.warning("Enter a name.")

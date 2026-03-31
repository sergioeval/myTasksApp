"""
Task tracker: task list on the main view; details in a large modal dialog.
"""
import html
import sqlite3
from datetime import date, datetime
import streamlit as st

import auth
import db

st.set_page_config(page_title="My tasks", layout="wide")
st.markdown(
    """
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
</style>
""",
    unsafe_allow_html=True,
)


def init():
    db.init_db()
    if "dialog_task_id" not in st.session_state:
        st.session_state.dialog_task_id = None
    if "general_tag_input_nonce" not in st.session_state:
        st.session_state.general_tag_input_nonce = 0


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


@st.dialog("New task", width="large")
def new_task_dialog() -> None:
    opts = db.status_options()
    if not opts:
        st.warning("Add at least one status under the **Statuses** tab first.")
        if st.button("Close", key="new_task_close_no_status"):
            st.rerun()
        return
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
        submitted = st.form_submit_button("Create task", type="primary")
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


@st.dialog("Manage tags", width="large")
def manage_general_tags_dialog() -> None:
    st.caption("Create, review, and delete tags used to organize general notes.")

    _tag_inp_key = f"inp_new_general_tag_{st.session_state.general_tag_input_nonce}"
    ec1, ec2 = st.columns([3, 1], vertical_alignment="bottom")
    with ec1:
        st.text_input(
            "New tag name",
            key=_tag_inp_key,
            placeholder="e.g. ideas, follow-up",
        )
    with ec2:
        if st.button("Create tag", use_container_width=True, type="primary", key="btn_create_general_tag"):
            raw = (st.session_state.get(_tag_inp_key) or "").strip()
            if raw:
                try:
                    db.add_tag(raw)
                    st.session_state.general_tag_input_nonce += 1
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("A tag with that name already exists.")
            else:
                st.warning("Enter a tag name.")

    st.divider()
    tags = db.list_tags()
    if not tags:
        st.caption("No tags yet.")
    else:
        st.markdown("**Existing tags**")
        for tg in tags:
            gc1, gc2 = st.columns([4, 1], vertical_alignment="center")
            with gc1:
                st.caption(tg["name"])
            with gc2:
                if st.button("Delete", key=f"dlg_del_tag_{tg['id']}", type="secondary"):
                    db.delete_tag(tg["id"])
                    st.rerun()


@st.dialog("Manage statuses", width="large")
def manage_statuses_dialog() -> None:
    st.caption("Add, rename, or delete statuses used by tasks.")

    with st.form("dlg_add_status", clear_on_submit=True):
        st.markdown("**Add status**")
        name = st.text_input("New status name", placeholder="e.g. To do")
        if st.form_submit_button("Add", type="primary"):
            if name.strip():
                try:
                    db.add_status(name)
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That name already exists.")
            else:
                st.warning("Enter a name.")

    st.divider()
    statuses = db.list_statuses()
    if not statuses:
        st.caption("No statuses yet.")
        return

    st.markdown("**Existing statuses**")
    for s in statuses:
        c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="center")
        with c1:
            new_name = st.text_input(
                "Name",
                value=s["name"],
                key=f"dlg_sn_{s['id']}",
                label_visibility="collapsed",
            )
        with c2:
            if st.button("Save", key=f"dlg_save_s_{s['id']}"):
                if new_name.strip():
                    db.update_status_name(s["id"], new_name)
                    st.rerun()
                else:
                    st.warning("Enter a name.")
        with c3:
            if st.button("Delete", key=f"dlg_del_s_{s['id']}", type="secondary"):
                if db.delete_status(s["id"]):
                    st.rerun()
                else:
                    st.error("Some tasks still use this status. Reassign them before deleting.")


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


if not auth.is_logged_in():
    auth.render_login_screen()
    st.stop()

init()
sync_open_task_from_query_params()

ht_left, ht_mid, ht_right = st.columns([4, 1, 1], vertical_alignment="center")
with ht_left:
    st.title("Task tracker")
with ht_mid:
    if st.button("New task", type="primary", use_container_width=True, key="open_new_task"):
        new_task_dialog()
with ht_right:
    if st.button("Log out", use_container_width=True, key="logout_btn"):
        auth.logout()

tab_tasks, tab_notes = st.tabs(["Tasks", "Notes"])

# --- Tab Tasks ---
with tab_tasks:
    cst1, cst2 = st.columns([4, 1], vertical_alignment="center")
    with cst1:
        st.subheader("Task list")
    with cst2:
        if st.button("Manage statuses", key="open_manage_statuses", use_container_width=True):
            manage_statuses_dialog()

    tasks = db.list_tasks()
    if not tasks:
        st.info("No tasks yet. Use **New task** above to add one.")
    else:
        st.caption(
            "Select a **status** to see its tasks as cards. "
            "Tasks are sorted by **priority** (lower number first). Click a **title** for details."
        )

        statuses = db.list_statuses()
        if not statuses:
            st.warning("No statuses are configured. Use **Manage statuses** to add one.")
        else:
            st.markdown(
                """
<style>
div.st-key-status_cards .stButton > button {
    min-height: 2.1rem !important;
    padding-top: 0.25rem !important;
    padding-bottom: 0.25rem !important;
    font-size: 0.95rem !important;
}
</style>
""",
                unsafe_allow_html=True,
            )

            status_ids_all = [s["id"] for s in statuses]
            status_labels = {s["id"]: s["name"] for s in statuses}

            def _task_card(t: dict) -> None:
                ttl = (t.get("title") or "").strip() or "—"
                desc = truncate_for_list(t.get("description"), max_len=120)
                pri = int(t.get("priority", 5))
                due_s = fmt_due(t.get("due_date"))
                due_in = fmt_days_until_due(t.get("due_date"))

                with st.container(border=True):
                    r1, r2 = st.columns([4, 1], vertical_alignment="center")
                    with r1:
                        btn_lbl = ttl if len(ttl) <= 52 else ttl[:49] + "…"
                        if st.button(
                            btn_lbl,
                            type="tertiary",
                            key=f"st_open_{t['id']}",
                            help=ttl if btn_lbl != ttl else None,
                            use_container_width=True,
                        ):
                            st.session_state.open_dialog_for_task = t["id"]
                            st.rerun()
                    with r2:
                        st.markdown(f"**P{pri}**")

                    st.caption(desc)
                    st.caption(f"Due: **{due_s}** · **{due_in}**")

                    cur_sid = t["status_id"]
                    new_sid = st.selectbox(
                        "Status",
                        options=status_ids_all,
                        index=status_ids_all.index(cur_sid) if cur_sid in status_ids_all else 0,
                        format_func=lambda sid: status_labels.get(sid, str(sid)),
                        key=f"st_move_{t['id']}",
                        label_visibility="collapsed",
                    )
                    if new_sid != cur_sid:
                        db.set_task_status(t["id"], int(new_sid))
                        st.rerun()

            # Group tasks by status_id (preserve current ordering)
            by_sid: dict[int, list[dict]] = {sid: [] for sid in status_ids_all}
            for t in tasks:
                by_sid.setdefault(t["status_id"], []).append(t)

            cards_per_row = 3
            with st.container(key="status_cards"):
                selected_sid = st.selectbox(
                    "Status",
                    options=status_ids_all,
                    format_func=lambda sid: status_labels.get(sid, str(sid)),
                    key="task_status_filter",
                )
                items = by_sid.get(selected_sid, [])
                st.caption(f"{len(items)} task(s)")
                if not items:
                    st.info("No tasks in this status.")
                else:
                    for start in range(0, len(items), cards_per_row):
                        cols = st.columns(cards_per_row, gap="medium")
                        chunk = items[start : start + cards_per_row]
                        for i in range(cards_per_row):
                            with cols[i]:
                                if i < len(chunk):
                                    _task_card(chunk[i])
                                else:
                                    st.markdown(
                                        "<div style='height:0.1rem'></div>",
                                        unsafe_allow_html=True,
                                    )

        forced_tid = st.session_state.pop("open_dialog_for_task", None)
        if forced_tid is not None and db.get_task(forced_tid):
            st.session_state.dialog_task_id = forced_tid

        dlg_id = st.session_state.dialog_task_id
        if dlg_id is not None:
            if db.get_task(dlg_id):
                task_detail_modal(dlg_id)
            else:
                st.session_state.dialog_task_id = None

# --- Tab General notes ---
with tab_notes:
    st.subheader("General notes")
    st.caption(
        "Notes are not tied to tasks. The **newest** note is on top. Use tags to organize; filter with the "
        "dropdown. Tag names are case-insensitive (duplicates are not allowed)."
    )

    all_tags = db.list_tags()
    tag_id_to_name = {t["id"]: t["name"] for t in all_tags}
    tag_ids_options = [t["id"] for t in all_tags]

    filter_options: list[int | None] = [None] + tag_ids_options
    filter_tag_id = st.selectbox(
        "Show notes tagged with",
        options=filter_options,
        format_func=lambda tid: "All notes" if tid is None else tag_id_to_name[tid],
        key="notes_filter_by_tag",
    )

    c_manage, _ = st.columns([1, 4])
    with c_manage:
        if st.button("Manage tags", key="open_manage_tags", use_container_width=True):
            manage_general_tags_dialog()

    with st.form("add_general_note", clear_on_submit=True):
        note_body = st.text_area(
            "New note",
            height=120,
            placeholder="Write a general note…",
        )
        picked_tags = st.multiselect(
            "Tags (optional)",
            options=tag_ids_options,
            format_func=lambda i: tag_id_to_name[i],
            key="form_new_note_tag_pick",
        )
        if st.form_submit_button("Add note", type="primary"):
            if note_body and note_body.strip():
                db.add_general_note(note_body, tag_ids=picked_tags)
                st.rerun()
            else:
                st.warning("Write something before adding.")

    notes = db.list_general_notes(filter_tag_id=filter_tag_id)
    if not notes:
        if filter_tag_id is not None:
            st.info("No notes with this tag. Choose **All notes** or pick another tag.")
        else:
            st.info("No general notes yet. Add one above.")
    else:
        for n in notes:
            safe = html.escape(n["body"] or "").replace("\n", "<br/>")
            tag_names = n.get("tags") or []
            tags_html = ""
            if tag_names:
                joined = ", ".join(html.escape(t["name"]) for t in tag_names)
                tags_html = (
                    f'<div style="margin-top:0.4rem;font-size:0.85rem;color:#4b5563;">'
                    f"<strong>Tags:</strong> {joined}</div>"
                )
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            with c1:
                st.markdown(
                    f'<div style="background:#eef1f6;padding:0.85rem;border-radius:8px;margin-bottom:0.35rem;'
                    f'border:1px solid #d8dee8;color:#111827;font-size:1rem;line-height:1.5;">'
                    f'<small style="color:#374151;font-weight:600;">{html.escape(fmt_ts(n["created_at"]))}</small><br/>'
                    f'<span style="color:#0f172a;display:block;margin-top:0.35rem;">{safe}</span>{tags_html}</div>',
                    unsafe_allow_html=True,
                )
                ms_key = f"edit_note_tags_{n['id']}"
                cur_tag_ids = [t["id"] for t in (n.get("tags") or [])]
                st.multiselect(
                    "Update tags",
                    options=tag_ids_options,
                    default=cur_tag_ids,
                    format_func=lambda i: tag_id_to_name[i],
                    key=ms_key,
                )
                if st.button("Save tags", key=f"save_note_tags_{n['id']}"):
                    db.set_note_tags(n["id"], list(st.session_state.get(ms_key, [])))
                    if ms_key in st.session_state:
                        del st.session_state[ms_key]
                    st.rerun()
            with c2:
                if st.button("Delete", key=f"del_gen_note_{n['id']}", type="secondary"):
                    db.delete_general_note(n["id"])
                    st.rerun()

"""
Task tracker: task list on the main view; details in a large modal dialog.
"""
import html
import psycopg2
from datetime import date, datetime
import streamlit as st

import auth
import db
import db_cache as dbc

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
    s = iso.isoformat() if hasattr(iso, "isoformat") else str(iso)
    return s.replace("T", " ").replace("+00:00", " UTC").replace("Z", " UTC")


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
    if dbc.get_task(*dbc.cache_args(), tid):
        st.session_state.open_dialog_for_task = tid
    try:
        del st.query_params["open_task"]
    except KeyError:
        pass


def on_dialog_dismiss():
    st.session_state.dialog_task_id = None


@st.dialog("New task", width="large")
def new_task_dialog() -> None:
    opts = dbc.status_options(*dbc.cache_args())
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
                dbc.bump_cache()
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
                    dbc.bump_cache()
                    st.rerun()
                except psycopg2.IntegrityError:
                    st.error("A tag with that name already exists.")
            else:
                st.warning("Enter a tag name.")

    st.divider()
    tags = dbc.list_tags(*dbc.cache_args())
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
                    dbc.bump_cache()
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
                    dbc.bump_cache()
                    st.rerun()
                except psycopg2.IntegrityError:
                    st.error("That name already exists.")
            else:
                st.warning("Enter a name.")

    st.divider()
    statuses = dbc.list_statuses(*dbc.cache_args())
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
                    dbc.bump_cache()
                    st.rerun()
                else:
                    st.warning("Enter a name.")
        with c3:
            if st.button("Delete", key=f"dlg_del_s_{s['id']}", type="secondary"):
                if db.delete_status(s["id"]):
                    dbc.bump_cache()
                    st.rerun()
                else:
                    st.error("Some tasks still use this status. Reassign them before deleting.")


@st.dialog("Task details", width="large", on_dismiss=on_dialog_dismiss)
def task_detail_modal(task_id: int):
    task = dbc.get_task(*dbc.cache_args(), task_id)
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

    opts = dbc.status_options(*dbc.cache_args())
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
            dbc.bump_cache()
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
            dbc.bump_cache()
            st.rerun()

    st.divider()
    st.markdown("**Comments**")
    comments = dbc.list_comments(*dbc.cache_args(), task["id"])
    if not comments:
        st.caption("No comments yet.")
    else:
        for c in comments:
            cc1, cc2 = st.columns([6, 1], vertical_alignment="center")
            with cc1:
                safe = html.escape(c["body"] or "").replace("\n", "<br/>")
                st.markdown(
                    f'<div style="background:#eef1f6;padding:0.85rem;border-radius:8px;margin-bottom:0.5rem;'
                    f'border:1px solid #d8dee8;color:#111827;font-size:1rem;line-height:1.5;">'
                    f'<small style="color:#374151;font-weight:600;">{html.escape(fmt_ts(c["created_at"]))}</small><br/>'
                    f'<span style="color:#0f172a;display:block;margin-top:0.35rem;">{safe}</span></div>',
                    unsafe_allow_html=True,
                )
            with cc2:
                if st.button("Delete", key=f"cmt_del_{c['id']}", type="secondary"):
                    db.delete_comment(int(c["id"]))
                    dbc.bump_cache()
                    st.rerun()

    with st.form(f"dlg_comment_{task_id}", clear_on_submit=True):
        body = st.text_area(
            "Add a comment",
            height=100,
            placeholder="Write a comment…",
        )
        if st.form_submit_button("Post comment"):
            if body and body.strip():
                db.add_comment(task["id"], body)
                dbc.bump_cache()
                st.rerun()
            else:
                st.warning("Enter some text before posting.")

    st.divider()
    st.markdown("**Checklist**")
    items = dbc.list_checklist_items(*dbc.cache_args(), task["id"])
    if not items:
        st.caption("No checklist items yet.")
    else:
        for it in items:
            cc1, cc2 = st.columns([6, 1], vertical_alignment="center")
            with cc1:
                lbl = it["body"] or ""
                checked = bool(it["is_done"])
                new_checked = st.checkbox(
                    lbl,
                    value=checked,
                    key=f"chk_item_{it['id']}",
                )
                if new_checked != checked:
                    db.set_checklist_item_done(it["id"], new_checked)
                    dbc.bump_cache()
                    st.rerun()
            with cc2:
                if st.button("Delete", key=f"chk_del_{it['id']}", type="secondary"):
                    db.delete_checklist_item(it["id"])
                    dbc.bump_cache()
                    st.rerun()

    with st.form(f"dlg_add_checklist_{task_id}", clear_on_submit=True):
        new_item = st.text_input("Add checklist item", placeholder="e.g. Call supplier…")
        if st.form_submit_button("Add item"):
            if new_item and new_item.strip():
                db.add_checklist_item(task["id"], new_item)
                dbc.bump_cache()
                st.rerun()
            else:
                st.warning("Enter an item before adding.")

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
            dbc.bump_cache()
            st.rerun()


@st.dialog("Edit note", width="large")
def edit_note_dialog(note_id: int) -> None:
    note = dbc.get_general_note(*dbc.cache_args(), note_id)
    if not note:
        st.error("This note no longer exists.")
        if st.button("Close", key="note_close_missing"):
            st.rerun()
        return

    all_tags = dbc.list_tags(*dbc.cache_args())
    tag_id_to_name = {t["id"]: t["name"] for t in all_tags}
    tag_ids_options = [t["id"] for t in all_tags]

    # Get tags for this one note using list_general_notes() enrichment.
    enriched = dbc.list_general_notes(*dbc.cache_args(), None)
    cur = next((n for n in enriched if n["id"] == note_id), None)
    cur_tag_ids = [t["id"] for t in (cur.get("tags") if cur else [])] if cur else []

    st.caption(f"Created: {fmt_ts(note.get('created_at'))} · ID `{note_id}`")

    with st.form(f"edit_note_{note_id}"):
        title = st.text_input("Title", value=note.get("title") or "Untitled", max_chars=200)
        body = st.text_area("Body", value=note.get("body") or "", height=180)
        tags = st.multiselect(
            "Tags",
            options=tag_ids_options,
            default=cur_tag_ids,
            format_func=lambda i: tag_id_to_name[i],
        )
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.form_submit_button("Save", type="primary", use_container_width=True):
                db.update_general_note(note_id, title, body)
                db.set_note_tags(note_id, list(tags))
                dbc.bump_cache()
                st.rerun()
        with c2:
            if st.form_submit_button("Delete note", type="secondary", use_container_width=True):
                db.delete_general_note(note_id)
                dbc.bump_cache()
                st.rerun()

if not auth.is_logged_in():
    auth.render_login_screen()
    st.stop()

init()
sync_open_task_from_query_params()

ht_left, ht_right = st.columns([5, 1], vertical_alignment="center")
with ht_left:
    st.title("Task tracker")
with ht_right:
    if st.button("Log out", use_container_width=True, key="logout_btn"):
        auth.logout()

tab_tasks, tab_notes = st.tabs(["Tasks", "Notes"])

# --- Tab Tasks ---
with tab_tasks:
    cst1, cst2, cst3 = st.columns([3, 1, 1], vertical_alignment="center")
    with cst1:
        st.subheader("Task list")
    with cst2:
        if st.button("New task", type="primary", key="open_new_task", use_container_width=True):
            new_task_dialog()
    with cst3:
        if st.button("Manage statuses", key="open_manage_statuses", use_container_width=True):
            manage_statuses_dialog()

    tasks = dbc.list_tasks(*dbc.cache_args())
    if not tasks:
        st.info("No tasks yet. Use **New task** to add one.")
    else:
        st.caption(
            "Select a **status** to see its tasks as cards. "
            "Tasks are sorted by **priority** (lower number first). Click a **title** for details."
        )

        statuses = dbc.list_statuses(*dbc.cache_args())
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
                        dbc.bump_cache()
                        st.rerun()

            # Group tasks by status_id (preserve current ordering)
            by_sid: dict[int, list[dict]] = {sid: [] for sid in status_ids_all}
            for t in tasks:
                by_sid.setdefault(t["status_id"], []).append(t)

            cards_per_row = 3
            with st.container(key="status_cards"):
                # Small summary of counts per status
                counts = {sid: len(by_sid.get(sid, [])) for sid in status_ids_all}
                st.markdown("**Summary**")
                sum_cols = st.columns(len(status_ids_all), gap="small")
                for col, sid in zip(sum_cols, status_ids_all):
                    with col:
                        with st.container(border=True):
                            st.caption(status_labels.get(sid, str(sid)))
                            st.markdown(f"### {counts.get(sid, 0)}")

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
        if forced_tid is not None and dbc.get_task(*dbc.cache_args(), forced_tid):
            st.session_state.dialog_task_id = forced_tid

        dlg_id = st.session_state.dialog_task_id
        if dlg_id is not None:
            if dbc.get_task(*dbc.cache_args(), dlg_id):
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

    all_tags = dbc.list_tags(*dbc.cache_args())
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
        note_title = st.text_input("Title", max_chars=200, placeholder="e.g. Meeting notes")
        note_body = st.text_area(
            "Body",
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
                db.add_general_note(note_title, note_body, tag_ids=picked_tags)
                dbc.bump_cache()
                st.rerun()
            else:
                st.warning("Write something before adding.")

    notes = dbc.list_general_notes(*dbc.cache_args(), filter_tag_id)
    if not notes:
        if filter_tag_id is not None:
            st.info("No notes with this tag. Choose **All notes** or pick another tag.")
        else:
            st.info("No general notes yet. Add one above.")
    else:
        cards_per_row = 3
        for start in range(0, len(notes), cards_per_row):
            cols = st.columns(cards_per_row, gap="medium")
            chunk = notes[start : start + cards_per_row]
            for i in range(cards_per_row):
                with cols[i]:
                    if i >= len(chunk):
                        st.markdown("<div style='height:0.1rem'></div>", unsafe_allow_html=True)
                        continue
                    n = chunk[i]
                    title = (n.get("title") or "").strip() or "Untitled"
                    body_txt = truncate_for_list(n.get("body"), max_len=240)
                    tag_names = n.get("tags") or []
                    tags_line = ", ".join(t["name"] for t in tag_names) if tag_names else "—"

                    with st.container(border=True):
                        if st.button(
                            title if len(title) <= 60 else title[:57] + "…",
                            key=f"note_open_{n['id']}",
                            type="tertiary",
                            use_container_width=True,
                            help=title,
                        ):
                            st.session_state.open_note_dialog_for = n["id"]
                            st.rerun()
                        st.caption(body_txt)
                        st.caption(f"Tags: **{tags_line}**")
                        st.caption(fmt_ts(n.get("created_at")))

    forced_note = st.session_state.pop("open_note_dialog_for", None)
    if forced_note is not None and dbc.get_general_note(*dbc.cache_args(), forced_note):
        edit_note_dialog(int(forced_note))

"""Cached reads for PostgreSQL via Streamlit ``st.cache_data``.

``st.cache_data`` is shared per server process, so each browser session gets a
unique ``sid`` in the cache key. ``epoch`` is bumped after any write so lists
and entity fetches stay consistent without waiting for TTL expiry.
"""
from __future__ import annotations

import uuid
from typing import Any

import streamlit as st

import db


def cache_args() -> tuple[int, str]:
    """Arguments to pass into every cached read (epoch + session id)."""
    k = "_streamlit_db_cache_sid"
    if k not in st.session_state:
        st.session_state[k] = str(uuid.uuid4())
    epoch = int(st.session_state.get("_streamlit_db_cache_epoch", 0))
    return epoch, st.session_state[k]


def bump_cache() -> None:
    """Invalidate read caches after a successful DB mutation in this session."""
    st.session_state["_streamlit_db_cache_epoch"] = (
        int(st.session_state.get("_streamlit_db_cache_epoch", 0)) + 1
    )


@st.cache_data(show_spinner=False)
def list_statuses(epoch: int, sid: str) -> list[dict[str, Any]]:
    return db.list_statuses()


@st.cache_data(show_spinner=False)
def list_tasks(epoch: int, sid: str) -> list[dict[str, Any]]:
    return db.list_tasks()


@st.cache_data(show_spinner=False)
def list_tags(epoch: int, sid: str) -> list[dict[str, Any]]:
    return db.list_tags()


@st.cache_data(show_spinner=False)
def list_general_notes(
    epoch: int, sid: str, filter_tag_id: int | None
) -> list[dict[str, Any]]:
    fid = None if filter_tag_id is None else int(filter_tag_id)
    return db.list_general_notes(filter_tag_id=fid)


@st.cache_data(show_spinner=False)
def status_options(epoch: int, sid: str):
    return db.status_options()


@st.cache_data(show_spinner=False)
def get_task(epoch: int, sid: str, task_id: int) -> dict[str, Any] | None:
    return db.get_task(int(task_id))


@st.cache_data(show_spinner=False)
def list_comments(epoch: int, sid: str, task_id: int) -> list[dict[str, Any]]:
    return db.list_comments(int(task_id))


@st.cache_data(show_spinner=False)
def list_checklist_items(
    epoch: int, sid: str, task_id: int
) -> list[dict[str, Any]]:
    return db.list_checklist_items(int(task_id))


@st.cache_data(show_spinner=False)
def get_general_note(
    epoch: int, sid: str, note_id: int
) -> dict[str, Any] | None:
    return db.get_general_note(int(note_id))

"""Simple session login against Streamlit secrets (no password storage in repo)."""
from __future__ import annotations

import hmac

import streamlit as st


def credentials_configured() -> bool:
    try:
        sec = st.secrets["auth"]
        u = str(sec.get("username", "")).strip()
        p = str(sec.get("password", ""))
        return bool(u and p)
    except Exception:
        return False


def verify_login(username: str, password: str) -> bool:
    if not credentials_configured():
        return False
    sec = st.secrets["auth"]
    u_ok = hmac.compare_digest(
        username.strip().encode("utf-8"),
        str(sec["username"]).encode("utf-8"),
    )
    p_ok = hmac.compare_digest(
        password.encode("utf-8"),
        str(sec["password"]).encode("utf-8"),
    )
    return u_ok and p_ok


def is_logged_in() -> bool:
    return bool(st.session_state.get("_taskapp_auth_ok"))


def set_logged_in(value: bool) -> None:
    st.session_state._taskapp_auth_ok = value


def render_login_screen() -> None:
    st.markdown(
        "#### Welcome to **Task tracker**  \n"
        "Sign in below to manage your tasks, statuses, and general notes in one place."
    )
    st.divider()
    st.title("Sign in")
    st.caption("Enter your credentials to continue.")
    if not credentials_configured():
        st.error(
            "Authentication is not configured. Add `.streamlit/secrets.toml` with an `[auth]` "
            "section (`username` and `password`). Copy from `.streamlit/secrets.toml.example`."
        )
        return
    with st.form("taskapp_login"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input(
            "Password",
            type="password",
            autocomplete="current-password",
        )
        if st.form_submit_button("Log in", type="primary"):
            if verify_login(username, password):
                set_logged_in(True)
                st.rerun()
            else:
                st.error("Invalid username or password.")


def logout() -> None:
    st.session_state.clear()
    st.rerun()

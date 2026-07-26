"""Cross-page session helpers for the Streamlit frontend."""
import streamlit as st


def keep_session_token() -> None:
    """Preserve the IdP ``session_token`` across page navigation and reloads.

    The token arrives once as a URL query param from the IdP redirect. Streamlit
    drops query params when navigating between multipage ``pages/`` (and on a full
    reload the query string is the only place it survives), which would otherwise
    log the user out as soon as they leave the landing page. So cache it in
    session_state on first sight and re-assert it into the URL on every run.

    Call this at the top of every page.
    """
    token = st.query_params.get("session_token") or st.session_state.get("session_token")
    if not token:
        return
    st.session_state["session_token"] = token
    if st.query_params.get("session_token") != token:
        st.query_params["session_token"] = token

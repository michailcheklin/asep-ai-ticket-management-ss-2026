"""Streamlit page (auto-served at :8501/faq) for submitting new FAQ entries.

Flow: fill the form -> submit. If the proposal is redundant, review the covering
entries and either proceed or cancel. Otherwise (or after "Dennoch anlegen") an
editable PREVIEW of the final entry (language-polished + generated title) is shown;
only after the user confirms it is actually stored.

UI chrome is localized (DE/EN) via ui.i18n; the stored FAQ content and the
category values stay in their stored language.
"""
import streamlit as st

from clients.live_client import LiveChatClient
from ui.i18n import get_language, t
from ui.session import keep_session_token

lang = get_language()

st.set_page_config(page_title=t("FAQ hinzufügen", lang), page_icon="📝")

# Keep the IdP session token alive when navigating here from the chat page.
keep_session_token()

client = LiveChatClient()

FORM_KEYS = ("faq_id", "faq_context", "faq_problem", "faq_solution")
PREV_KEYS = ("prev_id", "prev_context", "prev_problem", "prev_solution")
STATE_KEYS = ("faq_redundant", "faq_preview")

# Process a pending reset BEFORE any widget is instantiated (clearing widget-bound
# keys after the widgets are drawn does not reliably reset them on rerun).
if st.session_state.pop("_faq_clear", False):
    for _k in FORM_KEYS + PREV_KEYS + STATE_KEYS:
        st.session_state.pop(_k, None)


@st.cache_data(ttl=300)
def _load_contexts() -> list:
    """FAQ categories for the dropdown (cached; robust to backend being down)."""
    return LiveChatClient().get_faq_contexts()


def _build_payload(force: bool = False) -> dict:
    """Assemble the /faq payload from the form fields (initial submit)."""
    d = st.session_state
    solution = []
    if (d.get("faq_solution") or "").strip():
        solution = [{"faq_content": d["faq_solution"].strip(), "extracted_urls": []}]
    return {
        "id": (d.get("faq_id") or "").strip(),
        "context": (d.get("faq_context") or "").strip(),
        "problem": (d.get("faq_problem") or "").strip(),
        "solution": solution,
        "force": force,
    }


def _build_preview_payload() -> dict:
    """Assemble the confirm payload from the (possibly edited) preview fields."""
    d = st.session_state
    solution = []
    if (d.get("prev_solution") or "").strip():
        solution = [{"faq_content": d["prev_solution"].strip(), "extracted_urls": []}]
    return {
        "id": (d.get("prev_id") or "").strip(),
        "context": (d.get("prev_context") or "").strip(),
        "problem": (d.get("prev_problem") or "").strip(),
        "solution": solution,
        "confirmed": True,
    }


def _handle_response(res: dict, lang: str) -> None:
    """Translate a /faq response into session state (rendered after rerun)."""
    status = res.get("status")
    if status == "created":
        st.session_state["_faq_success_msg"] = t(
            "FAQ-Eintrag angelegt (Titel: {title}).", lang
        ).format(title=res.get("id"))
        st.session_state["_faq_clear"] = True
    elif status == "redundant":
        st.session_state["faq_redundant"] = res.get("matches", [])
    elif status == "preview":
        entry = res.get("entry", {})
        st.session_state.pop("faq_redundant", None)
        st.session_state["faq_preview"] = True
        st.session_state["prev_id"] = entry.get("id", "")
        st.session_state["prev_context"] = entry.get("context", "")
        st.session_state["prev_problem"] = entry.get("problem", "")
        st.session_state["prev_solution"] = " ".join(
            s.get("faq_content", "") for s in entry.get("solution", [])
            if isinstance(s, dict) and s.get("faq_content")
        )
    else:
        detail = res.get("detail") or t("Unbekannter Fehler", lang)
        st.session_state["_faq_error_msg"] = t("Fehler: {detail}", lang).format(detail=detail)


def _render_match(match: dict, lang: str) -> None:
    """Render one covering FAQ entry in a readable layout (values stay in the
    stored language; only the labels are UI)."""
    if match.get("context"):
        st.markdown(f"**{match['context']}**")
    st.markdown(t("**Titel:** {v}", lang).format(v=match.get("id", "")))
    if match.get("problem"):
        st.markdown(t("**Problem:** {v}", lang).format(v=match["problem"]))
    if match.get("solution"):
        st.markdown(t("**Lösung:** {v}", lang).format(v=match["solution"]))
    if match.get("last_update"):
        st.caption(match["last_update"])


def _render_form(lang: str) -> None:
    st.text_input(
        t("Titel:", lang),
        key="faq_id",
        help=t("Leer lassen — der Titel wird automatisch als Aussage erzeugt.", lang),
    )
    st.selectbox(
        t("Kategorie:", lang),
        options=_load_contexts(),
        index=None,
        placeholder=t("Kategorie wählen", lang),
        key="faq_context",
    )
    st.text_area(t("Problem:", lang), key="faq_problem", height=100)
    st.text_area(t("Lösung:", lang), key="faq_solution", height=200)

    if st.button(t("Vorschlag prüfen & absenden", lang), type="primary", use_container_width=True):
        category = (st.session_state.get("faq_context") or "").strip()
        problem = (st.session_state.get("faq_problem") or "").strip()
        solution = (st.session_state.get("faq_solution") or "").strip()
        if not (category and problem and solution):
            st.error(t("Bitte Kategorie, Problem und Lösung ausfüllen.", lang))
        else:
            _handle_response(client.submit_faq(_build_payload(force=False)), lang)
            st.rerun()

    # Redundancy review (only after a redundant submit).
    redundant = st.session_state.get("faq_redundant")
    if redundant:
        st.warning(t(
            "Dein Vorschlag scheint bereits durch folgende FAQ-Einträge abgedeckt zu sein. "
            "Bitte überdenke ihn – oder lege ihn dennoch an.", lang
        ))
        for match in redundant:
            header = t("{id} — Ähnlichkeit {similarity}", lang).format(
                id=match.get("id", "?"), similarity=f"{match.get('similarity', 0):.2f}"
            )
            with st.expander(header):
                _render_match(match, lang)

        col_create, col_cancel = st.columns(2)
        if col_create.button(t("Dennoch anlegen", lang), use_container_width=True):
            _handle_response(client.submit_faq(_build_payload(force=True)), lang)
            st.rerun()
        if col_cancel.button(t("Abbrechen", lang), use_container_width=True):
            st.session_state["_faq_clear"] = True
            st.rerun()


def _render_preview(lang: str) -> None:
    st.info(t("So wird der Eintrag gespeichert. Du kannst ihn hier noch anpassen.", lang))

    st.text_input(t("Titel:", lang), key="prev_id")
    # Ensure the (polished) category is selectable even if the list is unavailable.
    ctx_options = _load_contexts()
    current_ctx = st.session_state.get("prev_context") or ""
    if current_ctx and current_ctx not in ctx_options:
        ctx_options = [current_ctx] + ctx_options
    st.selectbox(t("Kategorie:", lang), options=ctx_options, key="prev_context")
    st.text_area(t("Problem:", lang), key="prev_problem", height=100)
    st.text_area(t("Lösung:", lang), key="prev_solution", height=200)

    col_save, col_cancel = st.columns(2)
    if col_save.button(t("Speichern bestätigen", lang), type="primary", use_container_width=True):
        category = (st.session_state.get("prev_context") or "").strip()
        problem = (st.session_state.get("prev_problem") or "").strip()
        solution = (st.session_state.get("prev_solution") or "").strip()
        if not (category and problem and solution):
            st.error(t("Bitte Kategorie, Problem und Lösung ausfüllen.", lang))
        else:
            _handle_response(client.submit_faq(_build_preview_payload()), lang)
            st.rerun()
    if col_cancel.button(t("Abbrechen", lang), use_container_width=True):
        st.session_state["_faq_clear"] = True
        st.rerun()


# --- Page ---------------------------------------------------------------------
st.title(t("📝 Neuen FAQ-Eintrag vorschlagen", lang))

_success = st.session_state.pop("_faq_success_msg", None)
if _success:
    st.success(_success)
_error = st.session_state.pop("_faq_error_msg", None)
if _error:
    st.error(_error)

if st.session_state.get("faq_preview"):
    _render_preview(lang)
else:
    st.caption(t(
        "Vorschläge werden vor dem Speichern gegen die bestehende FAQ-Datenbank auf "
        "Redundanz geprüft und sprachlich überarbeitet.", lang
    ))
    _render_form(lang)

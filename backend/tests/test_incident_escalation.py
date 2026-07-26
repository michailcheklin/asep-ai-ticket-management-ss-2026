"""
Offline tests for incident-to-problem escalation.

Testing is performed without actual Zammad or LLM calls:
  * the RAG logic in ``backend/rag/recent_incidents.py``
    (saving, semantic search, time window purge, deduplication)
  * the orchestration in ``ProblemService`` (Zammad/LLM are mocked)

The Chroma database runs in a temporary directory so that the actual
``recent_incidents_db`` remains untouched.

Run from ``backend/``:
    python tests/test_incident_escalation.py
or via pytest:
    pytest tests/test_incident_escalation.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

# Make the project root importable (backend as a package).
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.rag import recent_incidents  # noqa: E402
from backend.services.ProblemService import ProblemService  # noqa: E402

# --- Set up an isolated test database and configuration BEFORE the import ------------------
_TMP_DB = tempfile.mkdtemp(prefix="recent_incidents_test_")
os.environ["RECENT_INCIDENTS_DB_PATH"] = _TMP_DB
os.environ["INCIDENT_ESCALATION_MIN_COUNT"] = "5"
os.environ["INCIDENT_RECENCY_WINDOW_HOURS"] = "8"
os.environ["INCIDENT_SIMILARITY_THRESHOLD"] = "0.55"

# --- Test helpers -------------------------------------------------------
def check(label: str, condition: bool, detail: str = "") -> bool:
    """
    Write a message indicating whether a test condition has been met or not
    :param label: The name of the test
    :param condition: The condition to be tested
    :param detail: Additional information
    """
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f": {detail}" if detail else ""))
    return condition


def clear_collection() -> None:
    """
    Resets the temporary collection
    """
    col = recent_incidents.recent_incidents_collection
    ids = col.get().get("ids", []) or []
    if ids:
        col.delete(ids=ids)


# Five incidents that are (almost) identical in nature + one that is different.
WLAN_TEXTS = [
    "eduroam WLAN funktioniert nicht, ich bekomme keine Verbindung im Gebäude",
    "Kein WLAN-Zugang über eduroam, Verbindung schlägt ständig fehl",
    "eduroam verbindet sich nicht, WLAN geht seit heute nicht mehr",
    "WLAN eduroam bricht ab und ich komme nicht ins Uni-Netz",
    "eduroam lässt keine Verbindung zu, WLAN im Campus tot",
]
OTHER_TEXT = "Ich möchte eine Matlab-Lizenz für mein Studium beantragen"


def test_similarity_and_threshold() -> bool:
    """
    Checks whether the similarity search correctly applies the threshold
    :return: The test result indicating whether the test passed, as a Boolean
    """
    print("\n== Test 1: Similarity search + threshold ==")
    clear_collection()
    ok = True

    # Add four recent Wifi incidents
    for i, text in enumerate(WLAN_TEXTS[:4], start=101):
        recent_incidents.add_incident(ticket_id=i, text=text)

    # 5. Wi-Fi incident: if >=4 similar incidents are found -> escalation threshold reached
    recent_incidents.add_incident(ticket_id=105, text=WLAN_TEXTS[4])
    similar = recent_incidents.find_similar_open_incidents(
        text=WLAN_TEXTS[4], exclude_ticket_id=105
    )
    ok &= check("at least 4 similar WLAN incidents found",
                len(similar) >= 4, f"found={len(similar)}")
    ok &= check("threshold (>=5 incl. new) reached",
                len(similar) + 1 >= 5, f"count={len(similar) + 1}")

    # Incident with other topic: should NOT be escalated
    recent_incidents.add_incident(ticket_id=200, text=OTHER_TEXT)
    other_similar = recent_incidents.find_similar_open_incidents(
        text=OTHER_TEXT, exclude_ticket_id=200
    )
    ok &= check("unrelated incident finds no WLAN matches",
                len(other_similar) == 0, f"found={len(other_similar)}")
    return ok


def test_purge_stale() -> bool:
    """
    Checks whether old issues are no longer incorrectly marked as “Recent incident”
    :return: The test result indicating whether the test passed, as a Boolean
    """
    print("\n== Test 2: Time-window purge (>8h) ==")
    clear_collection()
    ok = True

    now = time.time()
    recent_incidents.add_incident(ticket_id=301, text=WLAN_TEXTS[0], created_at=now)
    # 9 hours old -> outside the 8-hour window
    recent_incidents.add_incident(ticket_id=302, text=WLAN_TEXTS[1],
                                  created_at=now - 9 * 3600)

    removed = recent_incidents.purge_stale_incidents(now=now)
    ok &= check("exactly 1 stale incident removed", removed == 1, f"removed={removed}")

    remaining = recent_incidents.recent_incidents_collection.get().get("ids", [])
    ok &= check("current incident is kept", "301" in remaining, f"ids={remaining}")
    ok &= check("stale incident is gone", "302" not in remaining, f"ids={remaining}")
    return ok


def test_dedup_existing_problem() -> bool:
    """
    Check whether an existing problem is detected, so that similar incidents do not create a second
    problem with the same subject matter
    :return: The test result indicating whether the test passed, as a Boolean
    """
    print("\n== Test 3: Dedup – detect existing problem ==")
    clear_collection()
    ok = True

    for i, text in enumerate(WLAN_TEXTS[:4], start=401):
        recent_incidents.add_incident(ticket_id=i, text=text)
    # Assign a incident to a problem
    recent_incidents.assign_incident_to_problem(401, problem_id=7777)

    similar = recent_incidents.find_similar_open_incidents(text=WLAN_TEXTS[0])
    existing = recent_incidents.find_existing_problem_id(similar)
    ok &= check("existing problem_id is detected", existing == 7777, f"found={existing}")
    return ok


def test_problem_service_escalation() -> bool:
    """
    Checks whether, when a problem needs to be escalated, this is done in ZIM as intended
    :return: The test result indicating whether the test passed, as a Boolean
    """
    print("\n== Test 4: ProblemService – escalation (Zammad/LLM mocked) ==")
    clear_collection()
    ok = True

    import backend.services.ProblemService as ps_mod

    created_tickets: list[dict] = []
    added_tags: list[tuple] = []

    def fake_create_system_ticket(title, body, author_email, priority=1, tags=None, group="Users"):
        """
        Mock of a ticket
        """
        created_tickets.append({"title": title, "priority": priority, "tags": tags})
        return 9999

    def fake_add_tag(ticket_id, tag):
        """
        Mock of adding a tag
        """
        added_tags.append((ticket_id, tag))

    def fake_add_article(*args, **kwargs):
        """
        Mock of adding an article
        """
        return None

    # Replace names directly bound to the ProblemService namespace
    ps_mod.create_system_ticket = fake_create_system_ticket
    ps_mod.add_tag_to_ticket = fake_add_tag
    ps_mod.add_article_to_ticket = fake_add_article

    service = ProblemService()
    service._derive_topic = lambda similar, text: "WLAN eduroam Ausfall"  # LLM umgehen

    # 4 Existing + 1 new Wi-Fi incident
    for i, text in enumerate(WLAN_TEXTS[:4], start=501):
        recent_incidents.add_incident(ticket_id=i, text=text)

    result = service.register_and_check_incident(
        ticket_id=505,
        issue_description=WLAN_TEXTS[4],
        additional_info=["Gebäude LF", "eduroam"],
    )

    ok &= check("escalated", result["escalated"] is True, str(result))
    ok &= check("new problem created", result["created"] is True, str(result))
    ok &= check("problem_id == 9999", result["problem_id"] == 9999, str(result))
    ok &= check("exactly 1 problem ticket created", len(created_tickets) == 1)
    ok &= check("problem ticket has high priority",
                created_tickets and created_tickets[0]["priority"] == 1)
    ok &= check("all 5 incidents tagged with problem tag",
                len([t for t in added_tags if t[1] == "problem:9999"]) == 5,
                f"tags={added_tags}")
    return ok


def test_problem_service_attach_existing() -> bool:
    """
    Checks whether an existing issue has been identified and whether other similar tickets are assigned to that issue
    :return:
    """
    print("\n== Test 5: ProblemService – attach to existing problem ==")
    clear_collection()
    ok = True

    import backend.services.ProblemService as ps_mod
    create_calls: list = []
    ps_mod.create_system_ticket = lambda **kw: create_calls.append(kw) or 1234
    ps_mod.add_tag_to_ticket = lambda *a, **k: None
    ps_mod.add_article_to_ticket = lambda *a, **k: None

    service = ProblemService()
    service._derive_topic = lambda similar, text: "WLAN eduroam Ausfall"

    # 4 existing ones, one of which has already been assigned to a problem (5555)
    for i, text in enumerate(WLAN_TEXTS[:4], start=601):
        recent_incidents.add_incident(ticket_id=i, text=text)
    recent_incidents.assign_incident_to_problem(601, problem_id=5555)

    result = service.register_and_check_incident(
        ticket_id=605,
        issue_description=WLAN_TEXTS[4],
        additional_info=[],
    )

    ok &= check("escalated", result["escalated"] is True, str(result))
    ok &= check("NO new problem created", result["created"] is False, str(result))
    ok &= check("existing problem_id 5555 used",
                result["problem_id"] == 5555, str(result))
    ok &= check("create_system_ticket NOT called", len(create_calls) == 0)
    return ok


def run_all() -> bool:
    """
    Runs all tests
    :return: The test result indicating whether all tests passed, as a Boolean
    """
    tests = [
        test_similarity_and_threshold,
        test_purge_stale,
        test_dedup_existing_problem,
        test_problem_service_escalation,
        test_problem_service_attach_existing,
    ]
    all_passed = True
    for t in tests:
        try:
            all_passed &= t()
        except Exception as e:
            print(f"  [FAIL] {t.__name__} raised: {e}")
            all_passed = False

    print("\n" + "=" * 60)
    print("RESULT: SUCCESS" if all_passed else "RESULT: FAILURE")
    print("=" * 60)
    return all_passed


def test_incident_escalation_suite():
    """
    Pytest start point
    """
    assert run_all()


if __name__ == "__main__":
    sys.exit(0 if run_all() else 1)

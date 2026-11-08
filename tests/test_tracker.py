"""Tracker logic and small helpers. No network or API key needed."""
import json

from meeting_agent import (
    already_processed,
    apply_outcomes,
    iso_date,
    load_tracker,
    open_items,
    overdue,
    render_owner_digests,
    save_tracker,
    slugify,
)

META = {"title": "Exec Weekly", "date": "2026-11-09", "attendees": "", "next_meeting": ""}


def outcome(actions=None, updates=None):
    return {"action_items": actions or [], "previous_item_updates": updates or []}


def action(task, owner="Mei Chen", due="2026-11-13"):
    return {
        "task": task, "owner": owner, "owner_basis": "explicit", "due_date": due,
        "priority": "high", "evidence": "said so", "timestamp": "00:00:21",
    }


def fresh():
    return {"next_id": 1, "items": [], "meetings": []}


def test_new_items_get_sequential_ids():
    tracker = fresh()
    new = apply_outcomes(tracker, outcome([action("A"), action("B")]), META)
    assert [i["id"] for i in new] == ["A001", "A002"]
    assert tracker["next_id"] == 3


def test_updates_change_status_and_record_history():
    tracker = fresh()
    apply_outcomes(tracker, outcome([action("A")]), META)
    apply_outcomes(tracker, outcome(updates=[{"id": "A001", "status": "done", "note": "shipped"}]), META)
    item = tracker["items"][0]
    assert item["status"] == "done"
    assert item["history"][-1]["note"] == "shipped"
    assert open_items(tracker) == []


def test_hallucinated_ids_are_ignored():
    tracker = fresh()
    apply_outcomes(tracker, outcome(updates=[{"id": "A999", "status": "done", "note": "x"}]), META)
    assert tracker["items"] == []


def test_deferred_stays_open_with_new_due_date():
    tracker = fresh()
    apply_outcomes(tracker, outcome([action("A")]), META)
    apply_outcomes(
        tracker,
        outcome(updates=[{"id": "A001", "status": "deferred", "note": "slipped", "new_due_date": "2026-11-20"}]),
        META,
    )
    assert tracker["items"][0]["status"] == "open"
    assert tracker["items"][0]["due_date"] == "2026-11-20"


def test_overdue_ignores_tbd_future_and_non_iso_dates():
    items = [
        {"id": "A001", "due_date": "2026-11-01"},
        {"id": "A002", "due_date": "TBD"},
        {"id": "A003", "due_date": "2026-12-01"},
        {"id": "A004", "due_date": "next Friday"},  # would sort wrongly as a string
        {"id": "A005", "due_date": ""},
    ]
    assert [i["id"] for i in overdue(items, "2026-11-08")] == ["A001"]


def test_save_and_load_roundtrip_is_atomic(tmp_path):
    path = tmp_path / "tracker.json"
    tracker = fresh()
    apply_outcomes(tracker, outcome([action("A")]), META)
    save_tracker(path, tracker)
    assert load_tracker(path)["items"][0]["task"] == "A"
    assert not (tmp_path / "tracker.json.tmp").exists()  # temp file was swapped into place


def test_load_tracker_upgrades_old_files_and_rejects_corrupt_ones(tmp_path):
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"next_id": 2, "items": []}))
    assert load_tracker(old)["meetings"] == []

    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    try:
        load_tracker(bad)
    except SystemExit as e:
        assert "not valid JSON" in str(e)
    else:
        raise AssertionError("expected SystemExit for a corrupt tracker")


def test_already_processed():
    tracker = fresh()
    tracker["meetings"].append({"fingerprint": "abc123"})
    assert already_processed(tracker, "abc123")
    assert not already_processed(tracker, "zzz")


def test_slugify_blocks_path_tricks():
    assert slugify("Exec Team Weekly") == "exec_team_weekly"
    assert slugify("../../etc/passwd") == "etc_passwd"
    assert slugify("///") == "meeting"


def test_iso_date_validation():
    assert iso_date("2026-11-09") == "2026-11-09"
    assert iso_date("") == ""
    try:
        iso_date("11/09/2026")
    except Exception as e:
        assert "expected a date" in str(e)
    else:
        raise AssertionError("expected an error for a non-ISO date")


def test_owner_digest_groups_open_items_by_owner():
    tracker = fresh()
    apply_outcomes(tracker, outcome([action("A", "Mei Chen"), action("B", "Raj Patel")]), META)
    tracker["items"][1]["status"] = "done"
    digest = render_owner_digests(tracker)
    assert "## Mei Chen" in digest and "Raj Patel" not in digest

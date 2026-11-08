"""Keeps sample/example_minutes.md honest: it must match what the renderer produces today.

If this fails after you change the report format, regenerate the file:
    python -m tests.test_example_output
"""
import json
from pathlib import Path

from meeting_agent import apply_outcomes, render_markdown

SAMPLE = Path(__file__).resolve().parent.parent / "sample"
META = {
    "title": "Exec Weekly",
    "date": "2026-11-09",
    "attendees": "Dana Smith (CEO), Raj Patel (CFO), Mei Chen (CTO), Luis Ortega (COO)",
    "next_meeting": "2026-11-16",
}
BANNER = (
    "> **Illustrative example.** Rendered by this project's code from a hand-written sample "
    "result (`example_outcomes.json`) to show the output format. This is not output from a "
    "live model run, and all names and company details are fictional."
)


def build_example() -> str:
    tracker = json.loads((SAMPLE / "example_prior_tracker.json").read_text(encoding="utf-8"))
    outcomes = json.loads((SAMPLE / "example_outcomes.json").read_text(encoding="utf-8"))
    new_items = apply_outcomes(tracker, outcomes, META)
    return render_markdown(outcomes, new_items, tracker, META)


def test_example_minutes_match_the_renderer():
    actual = (SAMPLE / "example_minutes.md").read_text(encoding="utf-8")
    assert actual.splitlines()[0] == BANNER
    assert actual.rstrip("\n").endswith(build_example()), (
        "sample/example_minutes.md is out of date. Regenerate with: python -m tests.test_example_output"
    )


def test_example_demonstrates_the_key_features():
    text = build_example()
    for heading in (
        "## Decisions",
        "## New Action Items",
        "## Updates on Previous Items",
        "## 🔴 Overdue Carryovers",
        "## 🔍 Please Verify Before Circulating",
        "## Proposed Agenda for Next Meeting",
    ):
        assert heading in text


if __name__ == "__main__":
    (SAMPLE / "example_minutes.md").write_text(BANNER + "\n\n" + build_example() + "\n", encoding="utf-8")
    print("Wrote sample/example_minutes.md")

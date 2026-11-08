"""Agent flow tests. The Anthropic client is mocked: no network, no API key, no cost."""
import contextlib
import io
import json
import os
import shutil
from pathlib import Path
from unittest import mock

import meeting_agent
from transcripts import load_source

SAMPLE = Path(__file__).resolve().parent.parent / "sample"
VTT = str(SAMPLE / "zoom_transcript.vtt")
NOTES = str(SAMPLE / "typed_notes.txt")
OUTCOMES = json.loads((SAMPLE / "example_outcomes.json").read_text(encoding="utf-8"))
META = {
    "title": "Exec Weekly",
    "date": "2026-11-09",
    "attendees": "Dana Smith (CEO), Raj Patel (CFO), Mei Chen (CTO), Luis Ortega (COO)",
    "next_meeting": "2026-11-16",
}


def fake_response(tool_input, stop_reason="tool_use"):
    block = mock.Mock()
    block.type = "tool_use"
    block.input = tool_input
    return mock.Mock(content=[block], stop_reason=stop_reason)


def fake_client(response):
    client = mock.Mock()
    client.messages.create.return_value = response
    return client


def run_main(argv, env=None):
    """Run main() quietly; return (stdout, SystemExit message or None)."""
    out = io.StringIO()
    message = None
    with mock.patch.dict(os.environ, env if env is not None else {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
        with contextlib.redirect_stdout(out):
            try:
                meeting_agent.main(argv)
            except SystemExit as e:
                message = str(e.code)
    return out.getvalue(), message


def base_args(tmp_path, *extra):
    return [
        VTT, NOTES,
        "--date", META["date"], "--title", META["title"],
        "--attendees", META["attendees"], "--next-meeting", META["next_meeting"],
        "--tracker", str(tmp_path / "tracker.json"), "--out", str(tmp_path / "out"),
        *extra,
    ]


def test_extract_outcomes_builds_prompt_and_forces_structured_output():
    client = fake_client(fake_response(OUTCOMES))
    prior = [{"id": "A001", "task": "Draft plan", "owner": "Mei Chen", "due_date": "2026-11-06", "status": "open"}]
    sources = [load_source(VTT), load_source(NOTES)]
    with mock.patch.object(meeting_agent.anthropic, "Anthropic", return_value=client):
        result = meeting_agent.extract_outcomes(sources, META, prior)

    assert result == OUTCOMES
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "record_meeting_outcomes"}
    prompt = kwargs["messages"][0]["content"]
    for expected in ("Dana Smith (CEO)", "A001", "<meeting_inputs>", 'type="transcript"', 'type="typed_notes"'):
        assert expected in prompt


def test_truncated_model_response_is_an_error():
    client = fake_client(fake_response(OUTCOMES, stop_reason="max_tokens"))
    with mock.patch.object(meeting_agent.anthropic, "Anthropic", return_value=client):
        try:
            meeting_agent.extract_outcomes([load_source(NOTES)], META, [])
        except RuntimeError as e:
            assert "cut off" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_incomplete_model_response_is_an_error():
    client = fake_client(fake_response({"summary": "only a summary"}))
    with mock.patch.object(meeting_agent.anthropic, "Anthropic", return_value=client):
        try:
            meeting_agent.extract_outcomes([load_source(NOTES)], META, [])
        except ValueError as e:
            assert "missing required fields" in str(e)
        else:
            raise AssertionError("expected ValueError")


def test_dry_run_calls_nothing_and_writes_nothing(tmp_path):
    with mock.patch.object(meeting_agent, "extract_outcomes", side_effect=AssertionError("API must not be called")):
        stdout, message = run_main(base_args(tmp_path, "--dry-run"), env={})  # no API key needed
    assert message is None
    assert "Speaker labels and talk time" in stdout
    assert not (tmp_path / "tracker.json").exists()
    assert not (tmp_path / "out").exists()


def test_missing_api_key_gives_a_clear_message(tmp_path):
    _, message = run_main(base_args(tmp_path), env={})
    assert message and "ANTHROPIC_API_KEY" in message and "--dry-run" in message


def test_end_to_end_with_carryover_and_duplicate_protection(tmp_path):
    shutil.copy(SAMPLE / "example_prior_tracker.json", tmp_path / "tracker.json")

    with mock.patch.object(meeting_agent, "extract_outcomes", return_value=OUTCOMES) as extract:
        _, message = run_main(base_args(tmp_path))
        assert message is None
        assert extract.call_count == 1

        out = tmp_path / "out"
        assert (out / "2026-11-09_exec_weekly.md").exists()
        assert (out / "2026-11-09_exec_weekly.json").exists()
        assert (out / "owner_digests.md").exists()
        assert not (tmp_path / "tracker.json.tmp").exists()

        tracker = json.loads((tmp_path / "tracker.json").read_text(encoding="utf-8"))
        status = {i["id"]: i["status"] for i in tracker["items"]}
        assert status["A003"] == "done" and status["A001"] == "blocked" and status["A002"] == "in_progress"
        assert [i["id"] for i in tracker["items"][3:]] == ["A004", "A005", "A006"]
        assert len(tracker["meetings"]) == 2

        # Same inputs again: refused before any API call, tracker unchanged.
        _, message = run_main(base_args(tmp_path))
        assert message and "already processed" in message
        assert extract.call_count == 1
        assert len(json.loads((tmp_path / "tracker.json").read_text(encoding="utf-8"))["items"]) == 6

        # --force overrides the guard.
        _, message = run_main(base_args(tmp_path, "--force"))
        assert message is None and extract.call_count == 2


def test_hostile_title_cannot_escape_output_directory(tmp_path):
    with mock.patch.object(meeting_agent, "extract_outcomes", return_value=OUTCOMES):
        args = base_args(tmp_path)
        args[args.index("--title") + 1] = "../../evil"
        _, message = run_main(args)
    assert message is None
    assert (tmp_path / "out" / "2026-11-09_evil.md").exists()
    assert not (tmp_path.parent / "evil.md").exists()


def test_invalid_date_is_rejected(tmp_path):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        _, message = run_main([VTT, "--date", "11/09/2026", "--dry-run"], env={})
    assert message == "2"  # argparse exits with status 2
    assert "expected a date" in err.getvalue()

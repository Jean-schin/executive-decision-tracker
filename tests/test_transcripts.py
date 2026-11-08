"""Parsing tests. All inputs are small synthetic examples with fictional names."""
from transcripts import fmt, load_source, render_sources, to_seconds


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_zoom_vtt_speakers_fillers_and_merge(tmp_path):
    path = write(tmp_path, "z.vtt", """WEBVTT

1
00:00:05.000 --> 00:00:08.000
Dana Smith: Okay, um, let's get started.

2
00:00:08.500 --> 00:00:12.000
Dana Smith: First item is launch.

3
00:00:12.500 --> 00:00:20.000
Raj Patel: Next steps: move it to the 15th.
""")
    src = load_source(path)
    assert src.kind == "transcript"
    assert set(src.speakers) == {"Dana Smith", "Raj Patel"}
    assert "um" not in src.body.lower().split()
    # consecutive lines from the same speaker are merged into one turn
    assert src.body.count("Dana Smith:") == 1
    # a sentence that merely starts with "Next steps:" is not mistaken for a speaker
    assert "Next steps" not in src.speakers
    assert "Raj Patel: Next steps: move it to the 15th." in src.body


def test_teams_vtt_voice_tags(tmp_path):
    path = write(tmp_path, "t.vtt", """WEBVTT

id-1/12-0
00:00:05.123 --> 00:00:08.456
<v Dana Smith>Let's start.</v>

id-1/13-0
00:00:09.000 --> 00:00:12.000
<v Raj Patel>Budget is 2.4 million.</v>
""")
    src = load_source(path)
    assert src.kind == "transcript"
    assert set(src.speakers) == {"Dana Smith", "Raj Patel"}
    assert "[00:00:09] Raj Patel: Budget is 2.4 million." in src.body


def test_zoom_txt_header_style(tmp_path):
    path = write(tmp_path, "z.txt", """[Dana Smith] 10:05:23
Let's start.

[Raj Patel] 10:05:30
I'll send the forecast Monday.

[Dana Smith] 10:06:10
Thanks.
""")
    src = load_source(path)
    assert src.kind == "transcript"
    # wall-clock times are made relative to the start of the meeting
    assert src.body.startswith("[00:00:00] Dana Smith:")


def test_teams_docx_style_text(tmp_path):
    path = write(tmp_path, "teams.txt", """Weekly Sync-Meeting Transcript
Dana Smith   0:05
Okay let's get started.
Raj Patel   0:12
I'll send the forecast Monday.
Dana Smith   0:40
Great, thanks.
""")
    src = load_source(path)
    assert src.kind == "transcript"
    assert set(src.speakers) == {"Dana Smith", "Raj Patel"}


def test_typed_notes_are_not_transcripts(tmp_path):
    path = write(tmp_path, "n.txt", "Exec weekly\n- Launch moved\n- Raj: forecast Monday\n")
    assert load_source(path).kind == "typed_notes"


def test_timed_agenda_is_not_a_transcript(tmp_path):
    path = write(tmp_path, "a.txt", "9:00 Intro\n9:15 Budget review\n9:30 Hiring update\n9:45 Wrap up\n")
    assert load_source(path).kind == "typed_notes"


def test_unlabeled_vtt_gets_unknown_speaker(tmp_path):
    path = write(tmp_path, "u.vtt", """WEBVTT

00:00:01.000 --> 00:00:03.000
We should ship on the 15th.

00:00:04.000 --> 00:00:06.000
Agreed.
""")
    assert set(load_source(path).speakers) == {"Unknown"}


def test_render_sources_includes_both_kinds(tmp_path):
    t = load_source(write(tmp_path, "z.vtt", "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nDana: Hi there.\n\n00:00:03.000 --> 00:00:04.000\nDana: Bye.\n"))
    n = load_source(write(tmp_path, "n.txt", "- a note\n"))
    out = render_sources([t, n])
    assert 'type="transcript"' in out and 'type="typed_notes"' in out


def test_time_helpers():
    assert to_seconds("00:01:05.500") == 65.5
    assert to_seconds("1:05") == 65
    assert fmt(3725) == "01:02:05"


def test_oversized_input_is_refused(tmp_path):
    path = write(tmp_path, "big.txt", "x" * 400_001)
    try:
        load_source(path)
    except SystemExit as e:
        assert "too large" in str(e)
    else:
        raise AssertionError("expected SystemExit for oversized input")


def test_bundled_sample_transcript_parses():
    from pathlib import Path
    src = load_source(str(Path(__file__).resolve().parent.parent / "sample" / "zoom_transcript.vtt"))
    assert src.kind == "transcript"
    assert set(src.speakers) == {"Dana Smith", "Raj Patel", "Mei Chen", "Luis Ortega"}

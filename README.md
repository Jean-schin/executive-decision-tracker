# Meeting Accountability Agent

A command-line tool that turns meeting notes and Zoom/Teams transcripts into decisions, owned
action items, status updates on earlier commitments, and a proposed agenda for the next meeting.
It is built to help a leadership team stay accountable between meetings.

It uses the Anthropic API for extraction and keeps a small local JSON tracker, so each meeting
builds on the last: open items carry over, overdue ones are flagged, and the next agenda is built
from what is still unresolved.

> **All sample data in this repository is fictional.** Names, the company ("Harborlight
> Robotics"), and meeting content are invented for demonstration.

## What it produces

- **Decisions**, separated from mere discussion, with rationale and a transcript timestamp.
- **Action items** with a single owner, a due date resolved from the meeting date, and
  supporting evidence. Ownership is tagged `explicit`, `inferred`, or `unassigned`, so unclear
  accountability is flagged instead of guessed.
- **Updates on earlier items** (done, in progress, blocked, deferred), applied only when the
  notes actually mention them.
- **A follow-up agenda** ordered by priority: decisions and blockers first, with a lead and a
  time box for each topic.
- **A "Please Verify" list** for things a human should check: misheard names or numbers,
  unidentified speakers, tentative commitments, and conflicts between typed notes and the
  transcript.

See [`sample/example_minutes.md`](sample/example_minutes.md) for the full output format. That file
is an **illustration**: it was rendered by this project's code from a hand-written sample result
(`sample/example_outcomes.json`), not produced by a live model run.

## Quick start

Requires Python 3.10+ and an [Anthropic API key](https://console.anthropic.com/).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export ANTHROPIC_API_KEY="your-key-here"   # keep this out of version control
```

Preview how your inputs are parsed. This makes no API call and writes no files:

```bash
python meeting_agent.py sample/zoom_transcript.vtt sample/typed_notes.txt --dry-run
```

Run it on the fictional sample meeting. Seeding the tracker with the sample's earlier action
items shows the carryover behaviour:

```bash
cp sample/example_prior_tracker.json tracker.json

python meeting_agent.py sample/zoom_transcript.vtt sample/typed_notes.txt \
  --date 2026-11-09 --title "Exec Weekly" \
  --attendees "Dana Smith (CEO), Raj Patel (CFO), Mei Chen (CTO), Luis Ortega (COO)" \
  --next-meeting 2026-11-16
```

Results are written to `out/`: the minutes (`.md`), the raw structured result (`.json`), and
`owner_digests.md` (what each person currently owns). Real model output will differ from the
illustration in `sample/example_minutes.md`.

### Options

| Option | Meaning |
|---|---|
| `inputs` | One or more files; a transcript and typed notes can be combined. `-` reads stdin. |
| `--date`, `--next-meeting` | `YYYY-MM-DD`. Relative dates in the notes ("by Friday") are resolved against `--date`. |
| `--attendees` | Helps map transcript speaker labels to people. |
| `--tracker`, `--out` | Tracker file (default `tracker.json`) and output folder (default `out`). |
| `--dry-run` | Parse and print the model input only. |
| `--force` | Reprocess inputs that were already processed (creates duplicate action items). |

## Supported inputs

| Source | Formats |
|---|---|
| Zoom | cloud-recording `.vtt`, audio-transcript `.txt` |
| Microsoft Teams | transcript `.vtt` (preferred), `.docx` download (best effort) |
| Generic | `.srt`, typed notes as `.txt`, `.md`, or `.docx` |

Transcripts are normalised before they reach the model: consecutive lines from one speaker are
merged, filler words are removed, timestamps are made relative to the start, and each speaker's
talk time is summarised. Reading `.docx` files needs `python-docx` (included in
`requirements.txt`).

## How it works

```
 transcripts / notes ─► transcripts.py ─► meeting_agent.py ─► Claude (forced tool call)
                          parse + clean      builds prompt         returns structured JSON
                                                  │
                                                  ▼
                               validate ─► update tracker.json ─► minutes, JSON, owner digests
```

Design choices worth knowing about:

- **Structured output via a forced tool call.** The model must answer through a JSON schema, so
  the result can be validated, stored, and rendered, with no free-text parsing.
- **No invented owners or deadlines.** The prompt tells the model to mark anything unclear as
  `UNASSIGNED` or `TBD`, and the report surfaces those items for confirmation.
- **Hedged language is not a commitment.** "Maybe I could look at that" becomes an open
  question, not a task.
- **Transcripts are data, not instructions.** The prompt tells the model to ignore commands
  embedded in the notes. This reduces, but does not eliminate, prompt-injection risk.
- **Safe re-runs.** Inputs are fingerprinted so the same meeting is not processed twice by
  accident, and the tracker is written atomically after the outputs.
- **Stable IDs.** Action items get IDs (`A001`, `A002`, ...) and a status history; unknown IDs
  returned by the model are ignored.

## Limitations

- **Review before sharing.** The output is a draft produced by a language model. Auto-generated
  captions contain errors, and the model can misjudge who committed to what. A person should
  read the minutes, especially the "Please Verify" section, before circulating them.
- **Parsers are tested on synthetic samples.** They were written for the common Zoom and Teams
  export layouts and are covered by unit tests using invented data. They have not been validated
  against a large set of real exports, and Teams `.docx` support in particular is best effort.
  If your export layout differs, please open an issue.
- **Single local tracker file.** There is no locking, so it is not meant for several people
  running it at once. It is also not integrated with task tools such as Jira or Asana.
- **No in-meeting chat logs** (for example Zoom's chat export), and one input file is limited to
  about 400,000 characters.
- **The model name is a constant** (`MODEL` at the top of `meeting_agent.py`). Change it if your
  API account uses a different model.

## Privacy and safety

- Transcript and note contents are sent to the Anthropic API. Check that this is permitted for
  the meetings you process.
- `.gitignore` excludes `tracker.json`, `out/`, `private/`, `.env`, and transcript files
  (`.vtt`, `.docx`) so real meeting content is not committed by accident. Only the fictional
  samples in `sample/` are allowed through.
- Never commit your API key. The tool reads it from the `ANTHROPIC_API_KEY` environment variable.

## Tests

```bash
pytest
```

The tests need no network access or API key; the Anthropic client is mocked. They cover transcript
parsing, tracker logic, the end-to-end flow (including carryover and duplicate protection), the
output format, and repository hygiene (README paths exist, no secrets, sample data labelled
fictional). GitHub Actions runs them on every push (see `.github/workflows/tests.yml`).

If you change the report format, regenerate the example output:

```bash
python -m tests.test_example_output
```

## Project layout

```
meeting_agent.py            CLI, prompt, tracker, and report rendering
transcripts.py              Zoom/Teams/notes loading and normalisation
requirements.txt            runtime dependencies
requirements-dev.txt        runtime + test dependencies
pytest.ini                  test configuration
sample/
  zoom_transcript.vtt         fictional Zoom-style transcript
  typed_notes.txt             fictional typed notes
  example_prior_tracker.json  fictional earlier action items
  example_outcomes.json       hand-written sample model result
  example_minutes.md          illustrative rendered report
tests/
  test_transcripts.py         parsing tests
  test_tracker.py             tracker and helper tests
  test_agent.py               mocked end-to-end tests
  test_example_output.py      keeps the example report in sync
  test_repo_hygiene.py        README paths, secrets, fictional data
.github/workflows/tests.yml continuous integration
```

## License

MIT. See [LICENSE](LICENSE).

# Meeting Accountability Agent

Turns meeting notes and Zoom/Teams transcripts into decisions, owned action items, status
updates on earlier commitments, and a proposed follow-up agenda. Action items persist in
`tracker.json` so each meeting builds on the last.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
export ANTHROPIC_API_KEY="your-key-here"
```

## Usage

```bash
# Check how your files are parsed (no API call, nothing saved)
python meeting_agent.py sample/zoom_transcript.vtt sample/typed_notes.txt --dry-run

# Real run
python meeting_agent.py sample/zoom_transcript.vtt sample/typed_notes.txt \
  --date 2026-11-08 --title "Exec Weekly" \
  --attendees "Dana Smith (CEO), Raj Patel (CFO), Mei Chen (CTO), Luis Ortega (COO)" \
  --next-meeting 2026-11-15
```

Outputs go to `out/`: minutes (`.md`), the raw structured result (`.json`), and
`owner_digests.md` (what each person currently owns).

## Supported inputs

Zoom `.vtt` / `.txt`, Teams `.vtt` / `.docx`, `.srt`, and typed notes (`.txt`, `.md`, `.docx`).
Pass several files at once to combine a transcript with typed notes.

## Tests

```bash
pytest
```

## Privacy

Transcripts are sent to the Anthropic API. `.gitignore` excludes `tracker.json`, `out/`,
`.env`, and transcript files so meeting content is not committed by accident. Keep the
repository private.

"""
Loads meeting inputs for the meeting agent and normalizes them.

Supported inputs
  .vtt   Zoom cloud-recording transcript ("Name: text") and Teams transcript ("<v Name>text</v>")
  .srt   Generic subtitle files (speaker labels used only if most cues carry them)
  .txt   Zoom audio transcript ("[Name] 00:01:23" header lines), or typed notes
  .docx  Teams "Download transcript" Word file (best effort; prefer .vtt) and typed notes
  other  Treated as typed notes (.md, .txt bullets, etc.)

Everything is converted to compact lines like:
    [00:12:45] Dana Smith: We'll move the launch to the 15th.
and a speaker talk-time summary, which helps the model map speaker labels to attendees.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TIME = r"(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?"
_TIME_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$")
_FILLER_RE = re.compile(r"\b(?:um+|uh+|erm|hmm+|mhm+)\b[,.]?\s*", re.IGNORECASE)
_V_TAG_RE = re.compile(r"<v(?:\.[\w.]+)?\s+([^>]+)>")

MAX_CHARS = 400_000  # ~100k tokens; far more than a multi-hour meeting


@dataclass
class Cue:
    start: float
    speaker: str
    text: str


@dataclass
class Source:
    name: str
    kind: str  # "transcript" or "typed_notes"
    body: str
    speakers: dict[str, int] = field(default_factory=dict)  # speaker -> word count
    duration: float = 0.0


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def to_seconds(ts: str) -> float:
    m = _TIME_RE.match(ts.strip())
    if not m:
        return 0.0
    h, mi, s, frac = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + (float("0." + frac) if frac else 0.0)


def fmt(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _looks_like_name(s: str) -> bool:
    s = s.strip()
    return 0 < len(s) <= 60 and len(s.split()) <= 5 and not re.search(r"[.?!,;]$", s)


def _clean(text: str) -> str:
    text = _FILLER_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# VTT / SRT (Zoom and Teams)
# --------------------------------------------------------------------------
def _parse_vtt(text: str) -> list[Cue]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    rows = []  # (start, tag_speaker, colon_speaker, colon_text, plain_text)
    for block in re.split(r"\n\s*\n", text):
        lines = block.split("\n")
        idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue  # header, NOTE block, etc.
        start = to_seconds(lines[idx].split("-->")[0])
        body = " ".join(l.strip() for l in lines[idx + 1 :] if l.strip())

        tag = _V_TAG_RE.search(body)
        tag_speaker = tag.group(1).strip() if tag else None
        plain = re.sub(r"<[^>]+>", "", body).strip()

        colon_speaker = colon_text = None
        m = re.match(r"^([^:]{1,60}):\s+(.*)$", plain)
        if m and _looks_like_name(m.group(1)):
            colon_speaker, colon_text = m.group(1).strip(), m.group(2)
        rows.append((start, tag_speaker, colon_speaker, colon_text, plain))

    # Only trust "Name: text" prefixes if most cues have them (avoids treating
    # a sentence like "Next steps: ..." as a speaker in unlabeled captions).
    with_colon = sum(1 for r in rows if r[2])
    trust_colon = rows and with_colon / len(rows) >= 0.6

    cues = []
    for start, tag_speaker, colon_speaker, colon_text, plain in rows:
        if tag_speaker:
            cues.append(Cue(start, tag_speaker, plain))
        elif trust_colon and colon_speaker:
            cues.append(Cue(start, colon_speaker, colon_text))
        else:
            cues.append(Cue(start, "Unknown", plain))
    return cues


# --------------------------------------------------------------------------
# Header-style text (Zoom .txt, Teams .docx text)
# --------------------------------------------------------------------------
_HEADER_PATTERNS = [
    re.compile(rf"^\[(?P<n>[^\]]+)\]\s+(?P<t>{TIME})\s*$"),  # [Name] 00:01:23   (Zoom txt)
    re.compile(rf"^(?P<t>{TIME})\s+(?P<n>[^\d\s].{{0,59}})$"),  # 0:01:23 Name
    re.compile(rf"^(?P<n>[^\d\s].{{0,59}}?)\s+(?P<t>{TIME})\s*$"),  # Name  0:01:23   (Teams docx)
]


def _detect_header_pattern(lines: list[str]):
    """Return the header pattern that fits this text, or None if it's not a transcript."""
    best, best_count = None, 0
    for pat in _HEADER_PATTERNS:
        names, count, with_body = [], 0, 0
        for i, line in enumerate(lines):
            m = pat.match(line.strip()) if line.strip() else None
            if m and _looks_like_name(m.group("n")):
                count += 1
                names.append(m.group("n").strip())
                nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if nxt and not any(p.match(nxt) for p in _HEADER_PATTERNS):
                    with_body += 1
        # A real transcript has repeated speakers; a timed agenda ("9:00 Intro") does not.
        repeated = any(c >= 2 for c in Counter(names).values())
        if count >= 3 and with_body >= 3 and repeated and count > best_count:
            best, best_count = pat, count
    return best


def _parse_header_style(text: str, pat) -> list[Cue]:
    cues: list[list] = []
    cur = None
    for line in text.splitlines():
        s = line.strip()
        m = pat.match(s) if s else None
        if m and _looks_like_name(m.group("n")):
            cur = [to_seconds(m.group("t")), m.group("n").strip(), []]
            cues.append(cur)
        elif s and cur is not None:
            cur[2].append(s)
    result = [Cue(t, n, " ".join(body)) for t, n, body in cues if body]
    if result:  # some exports use wall-clock time; make it relative to the start
        t0 = result[0].start
        result = [Cue(max(c.start - t0, 0), c.speaker, c.text) for c in result]
    return result


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def _read_docx(path: Path) -> str:
    try:
        import docx  # python-docx
    except ImportError as e:
        raise SystemExit("Reading .docx requires: pip install python-docx") from e
    d = docx.Document(str(path))
    return "\n".join(p.text for p in d.paragraphs)


def _merge(cues: list[Cue]) -> list[Cue]:
    merged: list[Cue] = []
    for c in cues:
        text = _clean(c.text)
        if not text:
            continue
        if merged and merged[-1].speaker == c.speaker:
            merged[-1].text += " " + text
        else:
            merged.append(Cue(c.start, c.speaker, text))
    return merged


def _to_transcript(name: str, cues: list[Cue]) -> Source:
    cues = _merge(cues)
    words = Counter()
    for c in cues:
        words[c.speaker] += len(c.text.split())
    body = "\n".join(f"[{fmt(c.start)}] {c.speaker}: {c.text}" for c in cues)
    return Source(
        name=name,
        kind="transcript",
        body=body,
        speakers=dict(words.most_common()),
        duration=cues[-1].start if cues else 0.0,
    )


def load_source(path: str, stdin_text: str | None = None) -> Source:
    """Load one input file (or stdin text) and classify it as transcript or typed notes."""
    if stdin_text is not None:
        name, ext, text = "stdin", "", stdin_text
    else:
        p = Path(path)
        name, ext = p.name, p.suffix.lower()
        text = _read_docx(p) if ext == ".docx" else p.read_text(encoding="utf-8-sig", errors="replace")

    if len(text) > MAX_CHARS:
        raise SystemExit(f"{name} is too large ({len(text):,} chars). Split it into parts and run per part.")

    head = text.lstrip("\ufeff").lstrip()[:20]
    if ext in (".vtt", ".srt") or head.startswith("WEBVTT") or re.search(rf"{TIME}\s*-->\s*{TIME}", text[:2000]):
        cues = _parse_vtt(text)
        if cues:
            return _to_transcript(name, cues)

    pat = _detect_header_pattern(text.splitlines())
    if pat is not None:
        cues = _parse_header_style(text, pat)
        if cues:
            return _to_transcript(name, cues)

    return Source(name=name, kind="typed_notes", body=text.strip())


def render_sources(sources: list[Source]) -> str:
    """Format all sources for the model prompt."""
    parts = []
    for s in sources:
        if s.kind == "transcript":
            total = sum(s.speakers.values()) or 1
            talk = "\n".join(
                f"  - {name}: {w:,} words ({w * 100 // total}%)" for name, w in s.speakers.items()
            )
            parts.append(
                f'<source type="transcript" file="{s.name}" length="{fmt(s.duration)}">\n'
                f"Speaker labels and talk time:\n{talk}\n\n{s.body}\n</source>"
            )
        else:
            parts.append(f'<source type="typed_notes" file="{s.name}">\n{s.body}\n</source>')
    return "\n\n".join(parts)

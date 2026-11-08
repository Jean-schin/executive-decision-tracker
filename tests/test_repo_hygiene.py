"""Guards for a public repository: working README paths, no secrets, fictional sample data."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "out", "private"}
SKIP_FILES = {"tracker.json", "test_repo_hygiene.py"}  # local data; this file contains the patterns
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".vtt", ".yml", ".yaml", ".ini", ".cfg", ".toml", ""}


def repo_text_files():
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT)
        if not p.is_file() or set(rel.parts[:-1]) & SKIP_DIRS or p.name in SKIP_FILES:
            continue
        if p.suffix.lower() in TEXT_SUFFIXES:
            yield p


def test_paths_mentioned_in_readme_exist():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    paths = set(re.findall(r"\b(?:sample|tests)/[\w./-]*\w", readme))
    paths |= set(re.findall(r"\b[\w-]+\.py\b", readme))
    assert paths, "README should reference sample files and modules"
    missing = sorted(p for p in paths if not (ROOT / p).exists() and not (ROOT / "tests" / p).exists())
    assert not missing, f"README mentions files that do not exist: {missing}"


def test_required_modules_and_tests_are_present():
    for name in ("meeting_agent.py", "transcripts.py", "requirements.txt", "LICENSE", "README.md"):
        assert (ROOT / name).exists(), f"missing {name}"
    assert list((ROOT / "tests").glob("test_*.py"))


SECRET_PATTERNS = {
    "Anthropic/OpenAI-style key": re.compile(r"sk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key block": re.compile(r"BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY"),
    "email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    # Placeholders such as "your-key-here" or "<key>" are fine; anything else key-like is not.
    "hard-coded key assignment": re.compile(r"(?i)api[_-]?key\s*=\s*['\"](?!your-|<|xxx|changeme)[^'\"]{8,}['\"]"),
    "local user path": re.compile(r"/Users/\w+|/home/\w+|C:\\Users"),
}


def test_no_secrets_emails_or_local_paths_in_repo_files():
    findings = []
    for p in repo_text_files():
        text = p.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{p.relative_to(ROOT)}: {label}")
    assert not findings, "Possible sensitive content: " + "; ".join(findings)


def test_sample_data_is_labelled_fictional():
    for name in ("typed_notes.txt", "example_minutes.md"):
        assert "fictional" in (ROOT / "sample" / name).read_text(encoding="utf-8").lower()

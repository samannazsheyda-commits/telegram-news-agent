from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".py", ".js", ".css", ".html", ".md", ".txt", ".json", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".conf", ".service", ".timer", ".sh", ".svg",
}
FORBIDDEN = (
    "saman" + "naz",
    "she" + "yda",
    "saman" + "naz.she" + "yda",
)


def test_repository_contains_no_legacy_personal_identity_fingerprint():
    hits = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Procfile"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        for token in FORBIDDEN:
            if token.lower() in text:
                hits.append(f"{path.relative_to(ROOT)}: {token}")
    assert not hits, "Legacy personal identity fingerprint remains:\n" + "\n".join(hits)

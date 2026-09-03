"""Парсинг файлов викторин/опросов и построение кнопок «Поделиться»."""
import re
from urllib.parse import quote

SEP_RE = re.compile(r"(?m)^\s*---\s*$")


def _blocks(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return []
    out = []
    for p in SEP_RE.split(raw):
        lines = [ln.rstrip() for ln in p.splitlines() if not ln.strip().startswith("#")]
        text = "\n".join(lines).strip()
        if text:
            out.append(text)
    return out


def load_quiz(path: str) -> list[dict]:
    """Блок: первая строка — вопрос, '- ' варианты, '* ' правильный, '!' объяснение.
    Возвращает [{q, options, correct, explanation}]."""
    res = []
    for b in _blocks(path):
        q, options, correct, expl = "", [], 0, ""
        for line in b.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("!"):
                expl = s[1:].strip()
            elif s.startswith("*"):
                options.append(s[1:].strip())
                correct = len(options) - 1
            elif s.startswith("-"):
                options.append(s[1:].strip())
            elif not q:
                q = s
        if q and len(options) >= 2:
            res.append({"q": q[:255], "options": [o[:100] for o in options[:10]],
                        "correct": min(correct, len(options) - 1), "explanation": expl[:200]})
    return res


def load_polls(path: str) -> list[dict]:
    """Блок: первая строка — вопрос, '- ' варианты (обычный опрос)."""
    res = []
    for b in _blocks(path):
        q, options = "", []
        for line in b.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("-") or s.startswith("*"):
                options.append(s[1:].strip())
            elif not q:
                q = s
        if q and len(options) >= 2:
            res.append({"q": q[:255], "options": [o[:100] for o in options[:10]]})
    return res


def share_url(channel_url: str, text: str) -> str:
    """Ссылка 'Поделиться постом' — главный вирусный механизм."""
    return f"https://t.me/share/url?url={quote(channel_url)}&text={quote(text[:200])}"

"""Шаблоны комментариев и очереди постов: загрузка, ротация, фильтры."""
import re

SEP = "---"


def load_blocks(path: str) -> list[str]:
    """Режет файл на блоки по строке-разделителю ---. Комментарии (#) выкидывает."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return []
    parts = re.split(r"(?m)^\s*---\s*$", raw)
    blocks = []
    for p in parts:
        lines = [ln for ln in p.splitlines() if not ln.strip().startswith("#")]
        text = "\n".join(lines).strip()
        if len(text) >= 10:
            blocks.append(text)
    return blocks


def pick_variant(count: int, usage: dict[int, int]) -> int:
    """Индекс шаблона: берём самый редко использованный (равномерная ротация)."""
    if count <= 0:
        return 0
    return min(range(count), key=lambda i: (usage.get(i, 0), i))


def render(template: str, channel: str, from_channel: bool) -> str:
    """Подставляет {channel}. Если комментируем от имени канала — упоминание канала убираем."""
    ch = "" if from_channel else (channel or "")
    text = template.replace("{channel}", ch)
    # чистим повисшие пробелы/строки от пустой подстановки
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def post_allowed(text: str, stopwords: list[str]) -> tuple[bool, str]:
    """Фильтр постов-доноров: реклама и конкурсы пропускаем."""
    low = (text or "").lower()
    for w in stopwords:
        if w and w in low:
            return False, f"стоп-слово: {w}"
    return True, ""

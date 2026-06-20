import html
import re


MESSENGER_REPLY_LIMIT = 1900
WIDGET_REPLY_LIMIT = 1800
VOICE_REPLY_LIMIT = 1200


def format_ai_reply(text, channel):
    if not text:
        return ""

    channel = str(channel).strip().lower()
    if channel == "messenger":
        return format_messenger_reply(text)
    if channel == "widget":
        return format_widget_reply(text)
    if channel == "voice":
        return format_voice_reply(text)
    raise ValueError(f"Unsupported AI reply channel: {channel}")


def format_messenger_reply(text):
    if not text:
        return ""

    text = _common_cleanup(text)
    text = _convert_markdown_tables(text, number_general_tables=True)
    text = _strip_markdown_emphasis(text)
    text = _replace_raw_table_pipes(text)
    text = _normalize_blank_lines(text)
    return _cap_reply(text, MESSENGER_REPLY_LIMIT)


def format_widget_reply(text):
    if not text:
        return ""

    text = _common_cleanup(text)
    return _cap_reply(text, WIDGET_REPLY_LIMIT)


def format_voice_reply(text):
    if not text:
        return ""

    text = _common_cleanup(text)
    text = _convert_markdown_tables(text, number_general_tables=False)
    text = _strip_markdown_emphasis(text)
    text = _replace_raw_table_pipes(text)
    text = _remove_visual_headings(text)
    text = _flatten_for_voice(text)
    return _cap_reply(text, VOICE_REPLY_LIMIT)


def _common_cleanup(text):
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?is)<think\b[^>]*>.*?</think>", "", text)
    text = re.sub(r"(?is)</?think\b[^>]*>", "", text)
    text = re.sub(r"(?m)^\s*```[\w-]*\s*$", "", text)
    text = _strip_html_preserving_breaks(text)
    text = html.unescape(text).replace("\xa0", " ")
    text = _strip_html_preserving_breaks(text)
    text = re.sub(r"!?\[([^\]]+)]\([^)]+\)", r"\1", text)
    text = _strip_initial_reasoning(text)
    return _normalize_blank_lines(text)


def _strip_html_preserving_breaks(text):
    text = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", text)
    text = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", text)
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*p\s*>", "\n\n", text)
    text = re.sub(r"(?i)<\s*p\b[^>]*>", "", text)
    text = re.sub(r"(?i)<\s*li\b[^>]*>", "- ", text)
    text = re.sub(r"(?i)</\s*(div|section|article|li|h[1-6]|tr)\s*>", "\n", text)
    return re.sub(r"(?s)<[^>]+>", "", text)


def _strip_initial_reasoning(text):
    paragraphs = re.split(r"\n\s*\n", text.strip())
    while paragraphs and _looks_like_internal_reasoning(paragraphs[0]):
        paragraphs.pop(0)
    return "\n\n".join(paragraphs)


def _looks_like_internal_reasoning(paragraph):
    value = " ".join(paragraph.lower().split())
    if not value:
        return True

    if "?" in value:
        return False

    explicit_markers = (
        "analysis:",
        "reasoning:",
        "internal:",
        "thought:",
    )
    if value.startswith(explicit_markers):
        return True

    first_person_process = (
        "i should ",
        "i need to ",
    )
    return value.startswith(first_person_process)


def _convert_markdown_tables(text, *, number_general_tables):
    lines = text.split("\n")
    converted = []
    index = 0

    while index < len(lines):
        if index + 1 < len(lines) and _is_table_line(lines[index]) and _is_separator_line(lines[index + 1]):
            headers = _parse_table_line(lines[index])
            index += 2
            rows = []
            while index < len(lines) and _is_table_line(lines[index]):
                rows.append(_parse_table_line(lines[index]))
                index += 1
            converted.extend(_format_table_rows(headers, rows, number_general_tables))
            continue

        converted.append(lines[index])
        index += 1

    return "\n".join(converted)


def _is_table_line(line):
    stripped = line.strip()
    return "|" in stripped and len(_parse_table_line(stripped)) >= 2


def _is_separator_line(line):
    cells = _parse_table_line(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _parse_table_line(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _format_table_rows(headers, rows, number_general_tables):
    if len(headers) >= 2 and headers[0].lower() == "field" and headers[1].lower() == "value":
        return [f"{row[0]}: {row[1]}" for row in rows if len(row) >= 2 and row[0] and row[1]]

    formatted = []
    for row_number, row in enumerate(rows, start=1):
        parts = []
        for header, value in zip(headers, row):
            if header and value:
                parts.append(f"{header}: {value}")
        if not parts:
            continue
        line = "; ".join(parts)
        if number_general_tables:
            line = f"{row_number}. {line}"
        formatted.append(line)
    return formatted


def _strip_markdown_emphasis(text):
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_\n]+)__", r"\1", text)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = re.sub(r"_([^_\n]+)_", r"\1", text)
    text = text.replace("**", "").replace("__", "").replace("*", "")
    return re.sub(r"(?<!\w)_(?=\S)|(?<=\S)_(?!\w)", "", text)


def _replace_raw_table_pipes(text):
    return "\n".join(re.sub(r"\s*\|\s*", " ", line).strip() for line in text.split("\n"))


def _remove_visual_headings(text):
    lines = text.split("\n")
    if len([line for line in lines if line.strip()]) <= 1:
        return text

    kept = []
    for line in lines:
        heading = re.sub(r"^#{1,6}\s*", "", line.strip()).strip()
        letters = re.sub(r"[^A-Za-z]", "", heading)
        if len(letters) >= 3 and heading == heading.upper() and ":" not in heading:
            continue
        kept.append(line)
    return "\n".join(kept)


def _flatten_for_voice(text):
    sentences = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        if not line:
            continue
        if not re.search(r"[.!?]$", line):
            line += "."
        sentences.append(line)
    return " ".join(sentences)


def _normalize_blank_lines(text):
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _cap_reply(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."

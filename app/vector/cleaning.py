from __future__ import annotations

import re

_NOISE_EXACT_LINES = {
    "skip to main content",
    "back to top",
    "menu",
    "search",
}
_NOISE_LINK_TEXT = {
    "home",
    "study",
    "research",
    "news",
    "events",
    "about",
    "contact",
    "search",
    "menu",
}
_NAVIGATION_PIPE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z &/-]*(\s+\|\s+[A-Za-z][A-Za-z &/-]*)+$")
_HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_MARKDOWN_LINK_ONLY_PATTERN = re.compile(r"^\[(?P<label>[^\]]+)\]\([^)]+\)$")


def clean_markdown(markdown: str) -> str:
    if not markdown.strip():
        return ""

    normalized_text = _HTML_COMMENT_PATTERN.sub("", markdown).replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines: list[str] = []
    previous_blank = False

    for raw_line in normalized_text.split("\n"):
        line = _normalize_inline_whitespace(raw_line)
        if not line:
            if not previous_blank and cleaned_lines:
                cleaned_lines.append("")
            previous_blank = True
            continue
        if _is_noise_line(line):
            continue
        cleaned_lines.append(line)
        previous_blank = False

    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()
    return "\n".join(cleaned_lines)


def _normalize_inline_whitespace(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value).strip()


def _is_noise_line(line: str) -> bool:
    lowered = line.lower()
    if lowered in _NOISE_EXACT_LINES:
        return True
    if _NAVIGATION_PIPE_PATTERN.match(line) and _looks_like_navigation_pipe(lowered):
        return True
    markdown_link_match = _MARKDOWN_LINK_ONLY_PATTERN.match(line)
    if markdown_link_match and markdown_link_match.group("label").strip().lower() in _NOISE_LINK_TEXT:
        return True
    if line.startswith("![]("):
        return True
    return False


def _looks_like_navigation_pipe(lowered: str) -> bool:
    parts = [part.strip() for part in lowered.split("|")]
    return len(parts) >= 2 and all(part in _NOISE_LINK_TEXT for part in parts)


"""Markdown to HTML rendering for Ribbon.

Pure string-to-string helpers. Nothing here touches the filesystem, the
request, or any shared state, so the whole renderer can be read and tested
on its own.
"""

from __future__ import annotations

import re
from html import escape, unescape
from pathlib import Path


def _safe_url(url: str) -> str:
    value = unescape(url).strip()
    if re.match(r"(?i)^(?:javascript|vbscript|data):", value):
        return "#"
    return url


def _inline_markdown(text: str) -> str:
    codes: list[str] = []

    def stash_code(match: re.Match) -> str:
        codes.append("<code>" + escape(match.group(1)) + "</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", stash_code, text)
    text = escape(text)

    def image(match: re.Match) -> str:
        alt = match.group(1)
        target = _safe_url(match.group(2).split()[0] if match.group(2).split() else "")
        return f'<img src="{target}" alt="{alt}" loading="lazy">'

    def link(match: re.Match) -> str:
        label = match.group(1)
        target = _safe_url(match.group(2).split()[0] if match.group(2).split() else "")
        return f'<a href="{target}">{label}</a>'

    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_\n]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"~~([^~\n]+)~~", r"<del>\1</del>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<em>\1</em>", text)
    for index, code in enumerate(codes):
        text = text.replace(f"\x00{index}\x00", code)
    return text


LIST_RE = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(.*)$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
SETEXT_RE = re.compile(r"^\s{0,3}(=+|-+)\s*$")
RULE_RE = re.compile(
    r"^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$"
)
TABLE_SEP_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)


def _table_cells(line: str) -> list[str]:
    row = line.strip()
    row = row.removeprefix("|")
    row = row.removesuffix("|")
    return [cell.strip() for cell in row.split("|")]


def _render_table(lines: list[str], index: int) -> tuple[str, int]:
    headers = _table_cells(lines[index])
    alignments: list[str] = []
    for cell in _table_cells(lines[index + 1]):
        if cell.startswith(":") and cell.endswith(":"):
            alignments.append("center")
        elif cell.endswith(":"):
            alignments.append("right")
        elif cell.startswith(":"):
            alignments.append("left")
        else:
            alignments.append("")
    index += 2
    rows: list[list[str]] = []
    while index < len(lines) and lines[index].strip() and "|" in lines[index]:
        rows.append(_table_cells(lines[index]))
        index += 1

    def cell(tag: str, value: str, position: int) -> str:
        align = alignments[position] if position < len(alignments) else ""
        style = f' style="text-align: {align}"' if align else ""
        return f"<{tag}{style}>{_inline_markdown(value)}</{tag}>"

    head = "".join(cell("th", value, i) for i, value in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(cell("td", value, i) for i, value in enumerate(row)) + "</tr>"
        for row in rows
    )
    table = (
        "<div class=\"rc-table-wrap\"><table><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )
    return table, index


def _render_list(lines: list[str], index: int) -> tuple[str, int]:
    first = LIST_RE.match(lines[index])
    assert first is not None
    base_indent = len(first.group(1))
    ordered = first.group(2)[0].isdigit()
    start_number = int(re.match(r"\d+", first.group(2)).group()) if ordered else 1
    items: list[str] = []

    while index < len(lines):
        match = LIST_RE.match(lines[index])
        if not match:
            break
        indent = len(match.group(1))
        marker = match.group(2)
        if indent != base_indent or marker[0].isdigit() != ordered:
            break
        content = [match.group(3)]
        item_indent = indent + len(marker) + 1
        index += 1
        while index < len(lines):
            following = lines[index]
            if not following.strip():
                lookahead = index
                while lookahead < len(lines) and not lines[lookahead].strip():
                    lookahead += 1
                if lookahead < len(lines):
                    next_item = LIST_RE.match(lines[lookahead])
                    if next_item and len(next_item.group(1)) == base_indent:
                        break
                    if next_item and len(next_item.group(1)) > base_indent:
                        content.append("")
                        index = lookahead
                        continue
                    if len(lines[lookahead]) - len(lines[lookahead].lstrip()) > base_indent:
                        content.append("")
                        index = lookahead
                        continue
                break
            next_item = LIST_RE.match(following)
            if next_item and len(next_item.group(1)) == base_indent:
                break
            leading = len(following) - len(following.lstrip())
            if leading > base_indent:
                content.append(
                    following[item_indent:]
                    if len(following) >= item_indent
                    else following.lstrip()
                )
                index += 1
                continue
            break
        items.append("\n".join(content))

    rendered: list[str] = []
    for item in items:
        task = ""
        task_match = re.match(r"^\[([ xX])\]\s+(.*)$", item, re.DOTALL)
        if task_match:
            checked = task_match.group(1).lower() == "x"
            task = '<input type="checkbox" disabled' + (" checked" if checked else "") + "> "
            item = task_match.group(2)
        body = _render_blocks(item).strip()
        if body.startswith("<p>"):
            end = body.find("</p>")
            if end != -1:
                body = body[3:end] + body[end + 4 :]
        rendered.append("<li>" + task + body + "</li>")

    if ordered:
        start = f' start="{start_number}"' if start_number != 1 else ""
        return "<ol" + start + ">" + "".join(rendered) + "</ol>", index
    return "<ul>" + "".join(rendered) + "</ul>", index


def _is_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not line.strip():
        return True
    if FENCE_RE.match(line) or HEADING_RE.match(line) or RULE_RE.match(line):
        return True
    if line.lstrip().startswith(">") or LIST_RE.match(line):
        return True
    if index + 1 < len(lines) and SETEXT_RE.match(lines[index + 1]):
        return True
    return "|" in line and index + 1 < len(lines) and bool(
        TABLE_SEP_RE.match(lines[index + 1])
    )


def _render_blocks(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            info = fence.group(2).strip()
            code: list[str] = []
            index += 1
            closing = re.compile(
                r"^\s{0,3}" + re.escape(marker[0]) + r"{" + str(len(marker)) + r",}\s*$"
            )
            while index < len(lines) and not closing.match(lines[index]):
                code.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            language = info.split()[0] if info else ""
            css = f' class="language-{escape(language)}"' if language else ""
            output.append(
                "<pre><code" + css + ">" + escape("\n".join(code)) + "</code></pre>"
            )
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            output.append(
                f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>"
            )
            index += 1
            continue

        if (
            index + 1 < len(lines)
            and SETEXT_RE.match(lines[index + 1])
            and line.strip()
            and not LIST_RE.match(line)
        ):
            level = 1 if lines[index + 1].strip().startswith("=") else 2
            output.append(
                f"<h{level}>{_inline_markdown(line.strip())}</h{level}>"
            )
            index += 2
            continue

        if RULE_RE.match(line):
            output.append("<hr>")
            index += 1
            continue

        if line.lstrip().startswith(">"):
            quote: list[str] = []
            while index < len(lines) and (
                lines[index].lstrip().startswith(">") or not lines[index].strip()
            ):
                quote.append(re.sub(r"^\s{0,3}>\s?", "", lines[index]))
                index += 1
            output.append(
                "<blockquote>" + _render_blocks("\n".join(quote)) + "</blockquote>"
            )
            continue

        if "|" in line and index + 1 < len(lines) and TABLE_SEP_RE.match(lines[index + 1]):
            table, index = _render_table(lines, index)
            output.append(table)
            continue

        if LIST_RE.match(line):
            listing, index = _render_list(lines, index)
            output.append(listing)
            continue

        if line.startswith(("    ", "\t")):
            code = []
            while index < len(lines) and (
                lines[index].startswith("    ")
                or lines[index].startswith("\t")
                or not lines[index].strip()
            ):
                code.append(
                    lines[index][4:]
                    if lines[index].startswith("    ")
                    else lines[index].lstrip("\t")
                )
                index += 1
            while code and not code[-1].strip():
                code.pop()
            output.append("<pre><code>" + escape("\n".join(code)) + "</code></pre>")
            continue

        paragraph = [line.strip()]
        index += 1
        while (
            index < len(lines)
            and lines[index].strip()
            and not _is_block_start(lines, index)
        ):
            paragraph.append(lines[index].strip())
            index += 1
        output.append("<p>" + _inline_markdown(" ".join(paragraph)) + "</p>")

    return "\n".join(output)


def render_markdown(text: str) -> str:
    return _render_blocks(text)


def markdown_view_html(rel_path: str, text: str) -> str:
    path = Path(rel_path)
    folder = path.parent.as_posix()
    folder_label = "/" if folder in ("", ".") else "/" + folder + "/"
    return (
        '<main class="rc-doc">'
        '<header class="rc-doc-head">'
        '<p class="rc-kicker">Markdown</p>'
        '<p class="rc-doc-path">'
        + escape(folder_label)
        + "<span>"
        + escape(path.name)
        + "</span></p>"
        "</header>"
        '<article class="rc-markdown">'
        + render_markdown(text)
        + "</article>"
        "</main>"
    )

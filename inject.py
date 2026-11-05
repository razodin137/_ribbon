"""Byte-level HTML tag scanning and the bar's page injection.

`iter_html_tags` skips comments, CDATA, declarations, processing instructions,
and the raw text of elements like <script> and <style>, so injection only ever
lands at a real tag. `inject_html` then puts the stylesheet at the end of the
head and the bar block just after the body opens.
"""

from __future__ import annotations

import re
from html import escape

import assets
from shell import BOOT_SCRIPT, PAGE_OFFSET_CSS, VIEW_TRANSITION_CSS


# Contents of these elements are text, not markup, so a <body> or </head>
# written inside one is not a real tag. The scanner below skips them.
RAW_TEXT_TAGS = frozenset(
    (
        b"script",
        b"style",
        b"textarea",
        b"title",
        b"xmp",
        b"iframe",
        b"noembed",
        b"noframes",
        b"noscript",
        b"plaintext",
    )
)


def iter_html_tags(data: bytes):
    """Yield (is_closing, name, start, end) for real tags in an HTML document.

    This is a small scanner, not a tree builder. It exists so injection never
    lands inside a comment or a script/style body, where a regex like
    rb"<body\\b[^>]*>" would happily match. It also skips CDATA, declarations
    such as <!DOCTYPE>, processing instructions, and the raw text of elements
    like <script>, <style>, <textarea>, and <title>. Attribute values are
    scanned with quote awareness, so a > inside a quoted value does not end a
    tag.
    """
    n = len(data)
    i = 0
    while i < n:
        start = data.find(b"<", i)
        if start < 0:
            return
        if data.startswith(b"<!--", start):
            close = data.find(b"-->", start + 4)
            i = n if close < 0 else close + 3
            continue
        if data.startswith(b"<![CDATA[", start):
            close = data.find(b"]]>", start + 9)
            i = n if close < 0 else close + 3
            continue
        if data.startswith(b"<!", start) or data.startswith(b"<?", start):
            close = data.find(b">", start + 2)
            i = n if close < 0 else close + 1
            continue

        j = start + 1
        closing = j < n and data[j : j + 1] == b"/"
        if closing:
            j += 1
        name_start = j
        while j < n:
            char = data[j : j + 1]
            if char.isspace() or char in (b">", b"/"):
                break
            j += 1
        name = data[name_start:j].lower()
        if not name or not name[0:1].isalpha():
            i = start + 1
            continue

        quote = b""
        while j < n:
            char = data[j : j + 1]
            if quote:
                if char == quote:
                    quote = b""
            elif char in (b'"', b"'"):
                quote = char
            elif char == b">":
                break
            j += 1
        if j >= n:
            return

        end = j + 1
        yield closing, name, start, end
        i = end
        if closing:
            continue
        if name == b"plaintext":
            return
        if name in RAW_TEXT_TAGS:
            close = re.search(
                rb"</" + re.escape(name) + rb"(?=[\s/>])", data[end:], re.IGNORECASE
            )
            if close is None:
                return
            i = end + close.start()


def html_injection_points(data: bytes) -> tuple[int | None, int | None, int | None]:
    """Where the style and the bar block belong in a page.

    Returns the end of the first real <body ...> tag, the start of the last
    real </head>, and the start of the last real </body>. Any of them is None
    when the document does not contain that tag.
    """
    body_open = None
    head_close = None
    body_close = None
    for closing, name, start, end in iter_html_tags(data):
        if closing:
            if name == b"head":
                head_close = start
            elif name == b"body":
                body_close = start
        elif name == b"body" and body_open is None:
            body_open = end
    return body_open, head_close, body_close


def inject_html(data: bytes, token: str = "", version: str = "") -> bytes:
    """Insert the bar's shell and scripts into a page.

    The stylesheet is metadata content, so it goes at the end of <head>.
    The rest of the block goes immediately after <body> so the bar is present
    at first paint instead of popping in. That placement is a trade-off: the
    injected bar host is body's first element child, so a page rule like
    `body > :first-child` matches it instead of the page's own first element,
    and sibling rules built on it skip over the rest of Ribbon's markup. Pages
    that style their first child by position should use a class. The page
    offset is a generated box on <html>, not a body child, so it stays out of
    the page's flex and grid layout. Pages with no <head> fall back to keeping
    the stylesheet in the body block.
    """
    if b"data-ribbon-host" in data or b"/__ribbon/ribbon.js" in data:
        return data
    attrs = b' data-ribbon="1"'
    if token:
        attrs += b' data-ribbon-token="' + escape(token).encode("utf-8") + b'"'
    style = (
        b"<style>"
        + VIEW_TRANSITION_CSS.encode("utf-8")
        + PAGE_OFFSET_CSS.encode("utf-8")
        + b"</style>"
    )
    inject = (
        assets.bar_shell_html()
        + BOOT_SCRIPT
        + b'<script src="' + assets.asset_url("bar.js", version).encode("utf-8") + b'" defer></script>'
        + b'<script src="' + assets.asset_url("ribbon.js", version).encode("utf-8") + b'"'
        + attrs
        + b" defer></script>"
    )
    body_open, head_close, body_close = html_injection_points(data)
    if head_close is not None:
        data = data[:head_close] + style + data[head_close:]
        if body_open is not None and head_close <= body_open:
            body_open += len(style)
        if body_close is not None and head_close <= body_close:
            body_close += len(style)
    else:
        inject = style + inject
    if body_open is not None:
        return data[:body_open] + inject + data[body_open:]
    if body_close is not None:
        return data[:body_close] + inject + data[body_close:]
    return data + inject

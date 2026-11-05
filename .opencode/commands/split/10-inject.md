---
description: Extract the tag scanner and injection into inject.py
---

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `inject.py` for the byte-level HTML tag scanner and injection.

## Cut

- `ribbon.py`: from `RAW_TEXT_TAGS` up to `BOOT_SCRIPT`
- `ribbon.py`: from `def iter_html_tags` up to `def state_home`

## Move

`RAW_TEXT_TAGS`, `iter_html_tags`, `html_injection_points`, `inject_html`.

## Depends on

`shell` for `BOOT_SCRIPT` and `VIEW_TRANSITION_CSS`, `assets` for
`bar_shell_html` and `asset_url`.

## Gotchas

- Keep the idempotency guard on `data-ribbon-host` and `/__ribbon/ribbon.js`
  byte-for-byte. It is a raw substring test over the whole document by design.
- Do not replace `iter_html_tags` with a regex. `test/injection.test.js` pins
  comments, CDATA, script strings, fake head and body closes, and a quoted `>`
  inside an attribute.
- The stylesheet is inserted before the body offsets are used, so both shift by
  `len(style)`. Preserve the ordering.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes and `injection.test.js` is green.

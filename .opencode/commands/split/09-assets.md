---
description: Extract embedded assets, serving and versioning into assets.py
---

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `assets.py` for the embedded asset block, serving and versioning.

## Cut

- `ribbon.py`: from `_EMBEDDED_ASSETS_B64` up to `def iter_html_tags`

## Move

The generated block between the two `# --- embedded assets ---` markers,
`DEV_ASSETS`, `_disk_asset_cache`, `embedded_asset`, `disk_asset`,
`asset_bytes`, `asset_stamp`, `missing_assets`, `bar_css`, `bar_shell_html`,
`_asset_version_cache`, `asset_version`, `asset_url`.

## Other files to change

- `build.py`: `TARGET` becomes `assets.py`, and the `START` and `END` markers
  move with the block.
- `main()`: replace `global DEV_ASSETS` and its assignment with
  `assets.DEV_ASSETS = args.dev`.
- The error string that says this `ribbon.py` has no embedded copy — point it at
  `assets.py`.

## Depends on

`config`, `shell`.

## Gotchas

- `build.py --check` runs inside `npm run check` and will fail until `TARGET`
  and the markers match.
- A `global` statement cannot reach another module, which is why `main()` must
  assign through the module.
- `bar_shell_html()` needs `BAR_MARKUP`, `BAR_HOST_STYLE`, `PAGE_OFFSET_CSS` and
  `VIEW_TRANSITION_CSS` from `shell.py`, so that extraction must have run.

## Done when

`npm run check` passes and `python3 build.py --check` reports the embed is
current.

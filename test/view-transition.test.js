import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

// Cross-document view transitions are configured in the page shell that
// ribbon.py injects. The opt-in and the bar's name have to sit in the
// document, not in the bar's shadow-root stylesheet.
const root = dirname(dirname(fileURLToPath(import.meta.url)))
const ribbon = readFileSync(join(root, "ribbon.py"), "utf8")
const start = ribbon.indexOf("VIEW_TRANSITION_CSS = (")
const end = ribbon.indexOf("BAR_MARKUP = ", start)
const transition = ribbon.slice(start, end)

test("pages opt in to cross-document view transitions", () => {
  assert.match(ribbon, /@view-transition \{ navigation: auto; \}/)
})

test("the bar keeps its name in both documents and does not cross-fade", () => {
  assert.match(ribbon, /view-transition-name:ribbon-bar!important/)
  assert.match(transition, /::view-transition-old\(ribbon-bar\)/)
  assert.match(transition, /::view-transition-new\(ribbon-bar\)/)
  assert.match(transition, /animation: none;/)
})

test("reduced motion turns the cross-document transition off", () => {
  const reduced = transition.slice(
    transition.indexOf("@media (prefers-reduced-motion: reduce)")
  )

  assert.ok(reduced.length > 0, "no reduced-motion block was found")
  assert.match(reduced, /@view-transition \{ navigation: none; \}/)
  assert.match(reduced, /::view-transition-old\(root\)/)
  assert.match(reduced, /::view-transition-new\(root\)/)
  assert.match(reduced, /animation: none;/)
})

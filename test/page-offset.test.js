import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

// The bar is fixed, so the page needs a strip of its own before the scripts
// run. The strip is a generated block on <html>, not a child of <body>, then
// hidden with the same host attribute that hides the bar when it is hidden by
// hand.
const root = dirname(dirname(fileURLToPath(import.meta.url)))
const read = (name) => readFileSync(join(root, name), "utf8")

const ribbonPy = read("ribbon.py")
const configPy = read("config.py")
const ribbonJs = read("ribbon.js")

test("the page reserves the bar's height before any script runs", () => {
  assert.match(configPy, /^BAR_HEIGHT = 40$/m)
  assert.match(ribbonPy, /PAGE_OFFSET_CSS = \(/)
  assert.match(ribbonPy, /html::before/)
  assert.match(ribbonPy, /height:\{BAR_HEIGHT\}px/)
  assert.match(
    ribbonPy,
    /VIEW_TRANSITION_CSS\.encode\("utf-8"\)\s*\+\s*PAGE_OFFSET_CSS\.encode\("utf-8"\)/
  )
})

test("the offset is not an in-flow body child", () => {
  assert.doesNotMatch(ribbonPy, /PAGE_OFFSET_MARKUP/)
  assert.doesNotMatch(ribbonPy, /data-ribbon-offset/)
})

test("hiding the bar by hand hides the page offset too", () => {
  assert.match(
    ribbonPy,
    /html:has\(\[data-ribbon-host\]\[data-ribbon-hidden\]\)::before/
  )
  assert.match(ribbonJs, /toggleAttribute\("data-ribbon-hidden", !on\)/)
  assert.doesNotMatch(ribbonJs, /host\.removeAttribute\("data-ribbon-hidden"\)/)
})

test("ribbon.js reads the height the server reserved", () => {
  assert.match(ribbonPy, /data-ribbon-height="'\s*\+\s*str\(BAR_HEIGHT\)/)
  assert.match(ribbonJs, /host\.getAttribute\("data-ribbon-height"\)/)
})

test("the host does not add body padding after load", () => {
  assert.doesNotMatch(ribbonJs, /savedPaddingTop/)
  assert.doesNotMatch(ribbonJs, /body\.style\.setProperty\(\s*"padding-top"/)
})

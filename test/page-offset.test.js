import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

// The bar is fixed, so the page needs a strip of its own before the scripts
// run. The offset is rendered by ribbon.py, then hidden with the same host
// attribute that hides the bar when the bar is hidden by hand.
const root = dirname(dirname(fileURLToPath(import.meta.url)))
const read = (name) => readFileSync(join(root, name), "utf8")

const ribbonPy = read("ribbon.py")
const ribbonJs = read("ribbon.js")

test("the page reserves the bar's height before any script runs", () => {
  assert.match(ribbonPy, /PAGE_OFFSET_MARKUP = \(/)
  assert.match(ribbonPy, /data-ribbon-offset/)
  assert.match(ribbonPy, /height:40px!important/)
  assert.match(ribbonPy, /bar_shell_html\(\)\s*\+\s*PAGE_OFFSET_MARKUP/)
})

test("hiding the bar by hand hides the page offset too", () => {
  assert.match(
    ribbonPy,
    /\[data-ribbon-host\]\[data-ribbon-hidden\] \+ \[data-ribbon-offset\]/
  )
  assert.match(ribbonJs, /toggleAttribute\("data-ribbon-hidden", !on\)/)
  assert.doesNotMatch(ribbonJs, /host\.removeAttribute\("data-ribbon-hidden"\)/)
})

test("the host does not add body padding after load", () => {
  assert.doesNotMatch(ribbonJs, /savedPaddingTop/)
  assert.doesNotMatch(ribbonJs, /body\.style\.setProperty\(\s*"padding-top"/)
})

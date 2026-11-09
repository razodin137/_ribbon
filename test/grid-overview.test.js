import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import vm from "node:vm"

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const read = (name) => readFileSync(join(root, name), "utf8")

const source = read("extension/newtab.js")
const page = read("extension/newtab.html")
const css = read("extension/newtab.css")
const cardJs = read("card.js")
const cardCss = read("card.css")
const barCss = read("bar.css")
const server = read("server.py")

function overviewUrl() {
  const start = source.indexOf("function overviewUrl(app, base) {")
  assert.notEqual(start, -1, "newtab.js has no overviewUrl()")
  const end = source.indexOf("\n  }", start)
  assert.notEqual(end, -1, "overviewUrl() is unterminated")
  const sandbox = {}
  vm.runInNewContext(
    'const CARD_ROUTE = "/__ribbon/card/"\n' +
      source.slice(start, end + 4) +
      "\nglobalThis.url = overviewUrl",
    sandbox,
    { filename: "newtab-overviewUrl.js" }
  )
  return sandbox.url
}

test("the overview URL points at the card route, encoded, without a bar", () => {
  const url = overviewUrl()
  const base = "http://127.0.0.1:8765"
  assert.equal(
    url({ path: "My App" }, base),
    "http://127.0.0.1:8765/__ribbon/card/My%20App/?embed=1"
  )
  assert.equal(
    url({ path: "a/b&c" }, base),
    "http://127.0.0.1:8765/__ribbon/card/a/b%26c/?embed=1"
  )
  assert.equal(url({ path: "/x/" }, base), "http://127.0.0.1:8765/__ribbon/card/x/?embed=1")
  assert.equal(url({}, base), "")
})

test("each card carries an overview button", () => {
  assert.match(source, /button\.className = "card-overview"/)
  assert.match(source, /shell\.append\(overviewButton\(app, base\)\)/)
  assert.match(source, /overviewEl\.showModal\(\)/)
  assert.match(css, /\.card-overview \{/)
})

test("the overview is a modal dialog shaped to the card", () => {
  assert.match(page, /<dialog class="overview" id="overview"/)
  assert.match(page, /<iframe class="overview-frame" id="overview-frame"/)
  assert.doesNotMatch(page, /overview-head/)
  assert.match(css, /\.overview::backdrop \{[^}]*backdrop-filter: blur\(14px\)/)
  assert.match(css, /\.overview \{[^}]*background: transparent;/)
  assert.match(css, /width: min\(680px, calc\(100vw - 32px\)\)/)
})

test("the embedded card reports its height and has no dark desk", () => {
  assert.match(server, /embed_class = ' class="rc-embed"' if embed else ""/)
  assert.match(cardCss, /html\.rc-embed,[\s\S]*?background: transparent;/)
  assert.match(cardJs, /type: "ribbon-card-size"/)
  assert.match(source, /data\.type !== "ribbon-card-size"/)
})

test("the in-app overview uses a cream translucent scrim", () => {
  assert.match(barCss, /background:\s*[\s\S]*?rgba\(246, 240, 226, \.78\)/)
  assert.match(barCss, /\.card-frame \{[^}]*background: transparent;/)
  assert.match(barCss, /:host\(\[data-card-open\]\) \.bar/)
  assert.match(css, /html:has\(dialog\.overview\[open\]\) \[data-ribbon-host\]/)
})

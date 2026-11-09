import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const read = (name) => readFileSync(join(root, name), "utf8")

function barMarkup(source) {
  const start = source.indexOf('BAR_MARKUP = "".join(')
  assert.notEqual(start, -1, "BAR_MARKUP is missing from shell.py")
  const open = source.indexOf('"""', start)
  const close = source.indexOf('"""', open + 3)
  assert.notEqual(close, -1, "BAR_MARKUP's markup string is unterminated")
  return source.slice(open + 3, close)
    .replace(/^\\\n/, "")
    .split("\n")
    .map((line) => line.trim())
    .join("")
}

const shell = barMarkup(read("shell.py"))
const barCss = read("bar.css")
const home = read("extension/home.js")
const newtab = read("extension/newtab.js")
const manifest = JSON.parse(read("extension/manifest.json"))
const build = read("build.py")

test("the bar's title carries a hidden home button next to the star", () => {
  assert.match(shell, /<span class="home-wrap" data-home hidden>/)
  assert.match(shell, /<a class="title-home" data-home-link href="#"/)
  assert.match(barCss, /\.home-wrap\[hidden\] \{ display: none; \}/)
  assert.doesNotMatch(shell, /menu-home/)
  assert.doesNotMatch(shell, /data-act="home"/)
  const star = shell.indexOf("title-star")
  const home = shell.indexOf("title-home")
  const title = shell.indexOf('class="title"')
  assert.ok(star !== -1 && home > star && title > home, "home sits between the star and the title")
})

test("the content script points home at the new tab page", () => {
  assert.match(home, /globalThis\.chrome\.runtime\.getURL\("newtab\.html"\)/)
  assert.match(home, /querySelector\("\[data-home\]"\)/)
  assert.match(home, /querySelector\("\[data-home-link\]"\)/)
  assert.match(home, /home\.hidden = false/)
})

test("the extension injects the content script and exposes the new tab page", () => {
  const script = manifest.content_scripts && manifest.content_scripts[0]
  assert.ok(script, "no content script is declared")
  assert.deepEqual(script.js, [ "home.js" ])
  assert.deepEqual(script.matches, [
    "http://127.0.0.1/*",
    "http://localhost/*",
    "http://[::1]/*"
  ])

  const exposed = manifest.web_accessible_resources && manifest.web_accessible_resources[0]
  assert.ok(exposed, "the new tab page is not web accessible")
  assert.ok(exposed.resources.includes("newtab.html"))
  assert.deepEqual(exposed.matches, script.matches)
})

test("the new tab page installs the same server bar", () => {
  const page = read("extension/newtab.html")
  assert.doesNotMatch(page, /class="ribbon"/)
  assert.match(newtab, /\/__ribbon\/bar\.html/)
  assert.match(newtab, /barScript\.src = "bar\.js"/)
  assert.match(newtab, /ribbonScript\.src = "ribbon\.js"/)
  assert.match(newtab, /data-ribbon-base/)
  assert.match(newtab, /data-ribbon-title", "home"/)
  assert.match(newtab, /data-ribbon-home/)
  assert.match(newtab, /globalThis\.chrome\.runtime\.getURL\("newtab\.html"\)/)
})

test("the build keeps the extension's bar copies in step", () => {
  assert.match(build, /COPIED = \("bar\.js", "ribbon\.js"\)/)
  assert.match(build, /EXTENSION_DIR/)
})

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import vm from "node:vm"

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const read = (name) => readFileSync(join(root, name), "utf8")

const barSource = read("bar.js")
const gridSource = read("extension/newtab.js")
const gridCss = read("extension/newtab.css")

const barSandbox = { window: {} }
vm.runInNewContext(barSource, barSandbox, { filename: "bar.js" })
const bar = barSandbox.window.__RIBBON_BAR__

function gridLights() {
  const start = gridSource.indexOf("function gitLights(git) {")
  assert.notEqual(start, -1, "newtab.js has no gitLights()")
  const end = gridSource.indexOf("\n  }", start)
  assert.notEqual(end, -1, "gitLights() is unterminated")
  const sandbox = {}
  vm.runInNewContext(
    gridSource.slice(start, end + 4) + "\nglobalThis.lights = gitLights",
    sandbox,
    { filename: "newtab-gitLights.js" }
  )
  return sandbox.lights
}

test("the grid's lights match the bar's lights", () => {
  const lights = gridLights()
  const cases = [
    {},
    { repo: false, state: "no-repo" },
    { repo: false, state: "error" },
    { repo: true, state: "clean" },
    { repo: true, state: "dirty", dirty: true, dirty_count: 2 },
    { repo: true, state: "dirty", files: [ "a" ] },
    { repo: true, state: "ahead", has_remote: true, ahead: 2 },
    { repo: true, state: "behind", has_remote: true, behind: 1 },
    { repo: true, state: "diverged", has_remote: true, ahead: 1, behind: 1 },
    { repo: true, state: "conflicted", has_remote: true },
    { repo: true, state: "no-upstream", has_remote: true },
    { repo: true, state: "detached", has_remote: true },
    { repo: true, state: "no-commits", has_remote: true },
    { repo: true, state: "clean", has_remote: true }
  ]
  for (const git of cases) {
    const plain = (value) => JSON.parse(JSON.stringify(value))
    assert.deepEqual(plain(lights(git)), plain(bar.gitLights(git)), JSON.stringify(git))
  }
})

test("a card shows all three dots, not just one status dot", () => {
  assert.match(gridSource, /dots\.className = "git-lights"/)
  assert.match(gridSource, /gitDot\(lights\.repoClass, repoTip\(git\)\)/)
  assert.match(gridSource, /gitDot\(lights\.changesClass, changesTip\(/)
  assert.match(gridSource, /gitDot\(lights\.remoteClass, remoteTip\(/)
  assert.match(gridCss, /\.git-lights \{/)
  assert.match(gridCss, /\.git-summary \{/)
})

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import vm from "node:vm"

// bar.js runs as a classic script. Give it the globals the pure layer needs,
// then drive trapTab with a small stand-in for a modal and its focusables.
const root = dirname(dirname(fileURLToPath(import.meta.url)))
const source = readFileSync(join(root, "bar.js"), "utf8")
const sandbox = { window: {} }
vm.runInNewContext(source, sandbox, { filename: "bar.js" })
const { trapTab } = sandbox.window.__RIBBON_BAR__

function makePanel(names) {
  const rootNode = { activeElement: null }
  const nodes = names.map(function (name) {
    const node = {
      name: name,
      hidden: false,
      getClientRects: function () { return [ {} ] },
      focus: function () { rootNode.activeElement = node }
    }
    return node
  })
  const panel = {
    getRootNode: function () { return rootNode },
    contains: function (node) { return nodes.indexOf(node) !== -1 },
    querySelectorAll: function () { return nodes }
  }
  return { panel: panel, nodes: nodes, rootNode: rootNode }
}

function press(key, shiftKey) {
  return {
    key: key,
    shiftKey: !!shiftKey,
    prevented: false,
    preventDefault: function () { this.prevented = true }
  }
}

test("Tab on the last control wraps to the first", () => {
  const { panel, nodes, rootNode } = makePanel([ "one", "two", "three" ])
  rootNode.activeElement = nodes[2]
  const event = press("Tab")
  assert.equal(trapTab(event, panel), true)
  assert.equal(event.prevented, true)
  assert.equal(rootNode.activeElement, nodes[0])
})

test("Shift+Tab on the first control wraps to the last", () => {
  const { panel, nodes, rootNode } = makePanel([ "one", "two", "three" ])
  rootNode.activeElement = nodes[0]
  const event = press("Tab", true)
  assert.equal(trapTab(event, panel), true)
  assert.equal(event.prevented, true)
  assert.equal(rootNode.activeElement, nodes[2])
})

test("Tab in the middle is left to the browser", () => {
  const { panel, nodes, rootNode } = makePanel([ "one", "two", "three" ])
  rootNode.activeElement = nodes[1]
  const event = press("Tab")
  assert.equal(trapTab(event, panel), true)
  assert.equal(event.prevented, false)
  assert.equal(rootNode.activeElement, nodes[1])
})

test("Tab pulls focus back when it escaped the panel", () => {
  const { panel, nodes, rootNode } = makePanel([ "one", "two" ])
  rootNode.activeElement = null
  const forward = press("Tab")
  trapTab(forward, panel)
  assert.equal(rootNode.activeElement, nodes[0])

  rootNode.activeElement = null
  const backward = press("Tab", true)
  trapTab(backward, panel)
  assert.equal(rootNode.activeElement, nodes[1])
})

test("a panel with no controls keeps Tab out", () => {
  const { panel } = makePanel([])
  const event = press("Tab")
  assert.equal(trapTab(event, panel), true)
  assert.equal(event.prevented, true)
})

test("hidden controls are skipped", () => {
  const { panel, nodes, rootNode } = makePanel([ "one", "two" ])
  nodes[1].hidden = true
  rootNode.activeElement = nodes[0]
  const event = press("Tab")
  trapTab(event, panel)
  assert.equal(event.prevented, true)
  assert.equal(rootNode.activeElement, nodes[0])
})

test("keys other than Tab are ignored", () => {
  const { panel, nodes, rootNode } = makePanel([ "one" ])
  rootNode.activeElement = nodes[0]
  const event = press("Enter")
  assert.equal(trapTab(event, panel), false)
  assert.equal(event.prevented, false)
})

test("a missing panel is ignored", () => {
  assert.equal(trapTab(press("Tab"), null), false)
})

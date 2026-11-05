import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const read = (name) => readFileSync(join(root, name), "utf8")

function definedNames(source) {
  const names = new Set()
  const pattern = /(?:^|\n)[ \t]*function\s+([A-Za-z0-9_$]+)\s*\(/g
  let match = pattern.exec(source)
  while (match) {
    names.add(match[1])
    match = pattern.exec(source)
  }
  return names
}

// Functions about the surface the bar sits on, not the bar itself. They are
// allowed to exist in both hosts because each host owns a different surface.
const HOST_ONLY = new Set([
  "onScroll", "processScroll", "reloadApp", "setManual", "toggleHidden"
])

// Duplicates that still exist at the time this guard was written. Shrink this
// list as the remaining packets land; the last test fails if an entry goes stale.
const PENDING = new Set([
  "readHidden"
])

const ribbon = definedNames(read("ribbon.js"))
const shell = definedNames(read("shell.js"))
const bar = definedNames(read("bar.js"))

test("no function that moved to bar.js is defined again in a host", () => {
  const redefined = [ ...bar ]
    .filter((name) => ribbon.has(name) || shell.has(name))
    .sort()
  assert.deepEqual(
    redefined,
    [],
    "these live in bar.js but are defined again in ribbon.js or shell.js"
  )
})

test("hosts only share the known pending or host-surface functions", () => {
  const shared = [ ...ribbon ]
    .filter((name) => shell.has(name))
    .sort()
  const unexpected = shared
    .filter((name) => !HOST_ONLY.has(name) && !PENDING.has(name))
  assert.deepEqual(
    unexpected,
    [],
    "new duplicate: move it to bar.js, or add it to HOST_ONLY with a reason"
  )
})

test("the PENDING list is not stale", () => {
  const shared = new Set([ ...ribbon ].filter((name) => shell.has(name)))
  const stale = [ ...PENDING ]
    .filter((name) => !shared.has(name))
    .sort()
  assert.deepEqual(
    stale,
    [],
    "no longer duplicated — remove these from PENDING in test/bar-duplication.test.js"
  )
})

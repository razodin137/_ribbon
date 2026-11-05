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

const ribbon = definedNames(read("ribbon.js"))
const bar = definedNames(read("bar.js"))

test("no function that lives in bar.js is defined again in the host", () => {
  const redefined = [ ...bar ]
    .filter((name) => ribbon.has(name))
    .sort()
  assert.deepEqual(
    redefined,
    [],
    "these live in bar.js but are defined again in ribbon.js"
  )
})

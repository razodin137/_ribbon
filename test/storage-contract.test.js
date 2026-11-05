import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

// BOOT_SCRIPT in shell.py runs before ribbon.js and reads the same session
// storage keys. The two halves have to agree or the bar flashes visible on
// every load, so pin them together here.
const root = dirname(dirname(fileURLToPath(import.meta.url)))

function jsConstant(ribbonJs, name) {
  const match = ribbonJs.match(new RegExp("const " + name + ' = "([^"]+)"'))
  assert.ok(match, name + " is missing from ribbon.js")
  return match[1]
}

function readContract() {
  const ribbonJs = readFileSync(join(root, "ribbon.js"), "utf8")
  const shellPy = readFileSync(join(root, "shell.py"), "utf8")

  const start = shellPy.indexOf("BOOT_SCRIPT = (")
  const end = shellPy.indexOf("\n)\n", start)
  assert.ok(start >= 0 && end > start, "BOOT_SCRIPT is missing from shell.py")

  return {
    ribbonJs: ribbonJs,
    storageKey: jsConstant(ribbonJs, "STORAGE_KEY"),
    scrollKey: jsConstant(ribbonJs, "SCROLL_KEY"),
    boot: shellPy.slice(start, end)
  }
}

// Read lazily inside the tests: a broken source file should fail a test, not
// crash the file before node:test gets a chance to report it.
let contract

function readOnce() {
  if (!contract) contract = readContract()
  return contract
}

test("the boot script reads the hidden key ribbon.js writes", () => {
  const { boot, storageKey } = readOnce()
  assert.ok(
    boot.includes('sessionStorage.getItem("' + storageKey + '")'),
    "BOOT_SCRIPT does not read " + storageKey
  )
})

test("the boot script tests for the value ribbon.js writes", () => {
  const { ribbonJs, boot, storageKey } = readOnce()
  const match = ribbonJs.match(
    /setItem\(STORAGE_KEY,\s*hidden\s*\?\s*"([^"]+)"\s*:\s*"([^"]+)"\)/
  )
  assert.ok(match, "ribbon.js does not write STORAGE_KEY as a flag")
  assert.ok(
    boot.includes('getItem("' + storageKey + '")==="' + match[1] + '"'),
    "BOOT_SCRIPT does not compare " + storageKey + " to " + match[1]
  )
})

test("the boot script compares the scroll key to the same location", () => {
  const { ribbonJs, boot, scrollKey } = readOnce()
  assert.match(ribbonJs, /sessionStorage\.setItem\(SCROLL_KEY, location\.href\)/)
  assert.ok(
    boot.includes('getItem("' + scrollKey + '")===location.href'),
    "BOOT_SCRIPT does not compare " + scrollKey + " to location.href"
  )
})

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

// The boot script sets the bar's initial state after the declarative shadow
// root has already resolved its starting style. The transition has to be off
// during that change or the bar animates away on every load.
const root = dirname(dirname(fileURLToPath(import.meta.url)))
const shellPy = readFileSync(join(root, "shell.py"), "utf8")
const barCss = readFileSync(join(root, "bar.css"), "utf8")

const start = shellPy.indexOf("BOOT_SCRIPT = (")
const end = shellPy.indexOf("\n)\n", start)
assert.ok(start >= 0 && end > start, "BOOT_SCRIPT is missing from shell.py")
const boot = shellPy.slice(start, end)

// The literal is a chain of byte strings, so join it the way Python would.
function bootScriptSource() {
  const lines = boot.match(/^\s*b(["'])(.*)\1\s*$/gm) || []
  const text = lines.map(function (line) {
    const quote = line.trim().charAt(1)
    return line.trim().slice(2, -1).replace(quote === '"' ? /\\"/g : /\\'/g, quote)
  }).join("")
  return text.slice(text.indexOf("<script>") + 8, text.lastIndexOf("</script>"))
}

test("the boot script is valid JavaScript", () => {
  assert.doesNotThrow(function () {
    new Function(bootScriptSource())
  })
})

test("the boot script turns transitions off before setting the hidden state", () => {
  const booting = boot.indexOf('h.setAttribute("data-ribbon-booting","")')
  const hidden = boot.indexOf('h.setAttribute("data-ribbon-hidden","")')

  assert.ok(booting >= 0, "BOOT_SCRIPT does not set data-ribbon-booting")
  assert.ok(hidden >= 0, "BOOT_SCRIPT does not set data-ribbon-hidden")
  assert.ok(booting < hidden, "data-ribbon-booting is set after data-ribbon-hidden")
})

test("the boot script removes data-ribbon-booting after two frames", () => {
  assert.match(
    boot,
    /requestAnimationFrame\(function\(\)\{requestAnimationFrame\(function\(\)\{[\s\S]*?h\.removeAttribute\("data-ribbon-booting"\)/
  )
})

test("the booting state disables the bar and peek transitions", () => {
  assert.match(barCss, /:host\(\[data-ribbon-booting\]\) \.bar/)
  assert.match(barCss, /:host\(\[data-ribbon-booting\]\) \.peek/)
  assert.match(
    barCss,
    /:host\(\[data-ribbon-booting\]\) \.bar,[\s\S]*?:host\(\[data-ribbon-booting\]\) \.peek \{[\s\S]*?transition: none;/
  )
})

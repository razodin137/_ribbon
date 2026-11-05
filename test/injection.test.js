import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import { dirname } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

// inject_html() scans bytes. These cases pin it to real tags only: a <body>
// in a comment or a JS string must not move the bar, and a fake </head> or
// </body> in a script must not split it.
const root = dirname(dirname(fileURLToPath(import.meta.url)))

const bridge = String.raw`
import json, sys
from ribbon import inject_html
cases = json.load(sys.stdin)
out = {}
for name, html in cases.items():
    out[name] = inject_html(html.encode("utf-8")).decode("utf-8")
print(json.dumps(out))
`

function inject(cases) {
  const result = spawnSync("python3", [ "-c", bridge ], {
    cwd: root,
    input: JSON.stringify(cases),
    encoding: "utf8"
  })
  assert.equal(result.status, 0, result.stderr)
  return JSON.parse(result.stdout)
}

test("a body tag inside a comment is left alone", () => {
  const out = inject({
    page: String.raw`<html><head></head><body><!-- <body class="fake"> --><p>hi</p></body></html>`
  }).page
  assert.match(out, /<body><div data-ribbon-host/)
  assert.match(out, /<!-- <body class="fake"> --><p>hi<\/p>/)
  assert.doesNotMatch(out, /<!-- <div data-ribbon-host/)
})

test("a body tag inside a script string does not break the script", () => {
  const out = inject({
    page: String.raw`<html><head></head><body><script>const sample = "<body class='x'>"</script></body></html>`
  }).page
  assert.match(out, /<body><div data-ribbon-host/)
  assert.match(out, /<script>const sample = "<body class='x'>"<\/script>/)
})

test("only the last real head close gets the stylesheet", () => {
  const out = inject({
    page: String.raw`<html><head><script>const s = "</head>"</script></head><body><p>hi</p></body></html>`
  }).page
  const script = out.indexOf(String.raw`const s = "</head>"`)
  const style = out.indexOf("<style>")
  const body = out.indexOf("<body>")
  assert.ok(script < style && style < body)
})

test("a head close inside a comment does not move the stylesheet", () => {
  const out = inject({
    page: String.raw`<html><head><!-- </head> --></head><body></body></html>`
  }).page
  assert.match(out, /<!-- <\/head> --><style>/)
})

test("the body close fallback skips a fake close in a script", () => {
  const out = inject({
    page: String.raw`<html><head></head><script>const s = "</body>"</script><p>hi</p></body></html>`
  }).page
  const script = out.indexOf(String.raw`const s = "</body>"`)
  const bar = out.indexOf("<div data-ribbon-host")
  const close = out.lastIndexOf("</body>")
  assert.ok(script < bar && bar < close)
})

test("a > inside a quoted body attribute does not end the tag early", () => {
  const out = inject({
    page: String.raw`<html><head></head><body data-x=">"><p>hi</p></body></html>`
  }).page
  assert.match(out, /<body data-x=">"><div data-ribbon-host/)
})

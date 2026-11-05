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

// shell.py paints the shell, then ribbon.js finds its pieces by selector. A
// class or data attribute renamed on one side only turns every lookup into
// null, so check the pair here. The README calls these the bar's two halves.

const shell = barMarkup(read("shell.py"))
const selectors = staticShadowSelectors(read("ribbon.js"))

test("the markup guard can read the shell and the host", () => {
  assert.ok(shell.includes('class="bar"'), "BAR_MARKUP was not read from shell.py")
  assert.ok(selectors.length > 20, "no static selectors were found in ribbon.js")
})

test("every static selector in the host exists in the bar markup", () => {
  const tree = parseMarkup(shell)
  const missing = selectors
    .filter((selector) => !matches(tree, selector))
    .sort()
  assert.deepEqual(
    missing,
    [],
    "these selectors match nothing in BAR_MARKUP"
  )
})

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

function staticShadowSelectors(source) {
  const pattern = /shadow\.querySelector(?:All)?\(\s*("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')\s*\)/g
  const found = []
  let match = pattern.exec(source)
  while (match) {
    found.push(match[1].slice(1, -1))
    match = pattern.exec(source)
  }
  return found
}

const VOID_TAGS = new Set(
  "area base br col embed hr img input link meta param source track wbr".split(" ")
)

function parseMarkup(html) {
  const root = { tag: "#root", attrs: {}, children: [], parent: null }
  let current = root
  const pattern = /<(\/?)([A-Za-z][-A-Za-z0-9]*)([^>]*?)(\/?)>/g
  let match = pattern.exec(html)
  while (match) {
    const [ , closing, tag, rawAttrs, selfClosing ] = match
    if (closing) {
      if (current.tag === tag) current = current.parent
    } else {
      const element = {
        tag: tag.toLowerCase(),
        attrs: parseAttributes(rawAttrs),
        children: [],
        parent: current
      }
      current.children.push(element)
      if (!selfClosing && !VOID_TAGS.has(element.tag)) current = element
    }
    match = pattern.exec(html)
  }
  return root
}

function parseAttributes(raw) {
  const attrs = {}
  const pattern = /([-A-Za-z0-9_:.]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g
  let match = pattern.exec(raw)
  while (match) {
    const value = match[2] ?? match[3] ?? match[4] ?? ""
    attrs[match[1].toLowerCase()] = value
    match = pattern.exec(raw)
  }
  return attrs
}

function matches(tree, selector) {
  const parts = selector.trim().split(/\s+/).map((text) => compound(text, selector))
  const stack = [ ...tree.children ]
  while (stack.length) {
    const element = stack.pop()
    if (matchesParts(element, parts)) return true
    stack.push(...element.children)
  }
  return false
}

function compound(text, selector) {
  const head = /^([A-Za-z][-A-Za-z0-9]*)?/.exec(text)
  const simple = {
    tag: head[1] ? head[1].toLowerCase() : null,
    classes: [],
    id: null,
    attrs: []
  }
  let rest = text.slice(head[0].length)
  while (rest) {
    const piece = /^\.([-A-Za-z0-9_]+)|^#([-A-Za-z0-9_]+)|^\[([^\]]+)\]/.exec(rest)
    if (!piece) {
      throw new Error(selector + ": the markup guard cannot read " + JSON.stringify(rest))
    }
    if (piece[1]) simple.classes.push(piece[1])
    else if (piece[2]) simple.id = piece[2]
    else {
      const attr = /^([-A-Za-z0-9_:.]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\]\s]+)))?$/.exec(piece[3])
      if (!attr) {
        throw new Error(selector + ": the markup guard cannot read " + JSON.stringify(piece[3]))
      }
      simple.attrs.push([ attr[1].toLowerCase(), attr[2] ?? attr[3] ?? attr[4] ?? null ])
    }
    rest = rest.slice(piece[0].length)
  }
  return simple
}

function matchesParts(element, parts) {
  if (!matchesCompound(element, parts[parts.length - 1])) return false
  if (parts.length === 1) return true
  for (let parent = element.parent; parent && parent.tag !== "#root"; parent = parent.parent) {
    if (matchesParts(parent, parts.slice(0, -1))) return true
  }
  return false
}

function matchesCompound(element, simple) {
  if (simple.tag && element.tag !== simple.tag) return false
  if (simple.id && element.attrs.id !== simple.id) return false
  const classes = (element.attrs.class || "").split(/\s+/)
  if (!simple.classes.every((name) => classes.includes(name))) return false
  return simple.attrs.every(([ name, value ]) =>
    name in element.attrs && (value === null || element.attrs[name] === value)
  )
}

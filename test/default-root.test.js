import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import { mkdirSync, mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"

// default_root() guesses the folder to serve. A guess that lands too high is
// served as static files, so the filesystem root, a home folder, and system
// folders must never be guessed. --root is still allowed to point anywhere.
const root = dirname(dirname(fileURLToPath(import.meta.url)))

function runPython(lines) {
  return execFileSync("python3", [ "-c", lines.join("\n") ], {
    cwd: root,
    encoding: "utf8"
  }).trim()
}

function defaultRootFor(appDir, home) {
  const output = runPython([
    "import json, pathlib, ribbon",
    "pathlib.Path.home = classmethod(lambda cls: pathlib.Path(" +
      JSON.stringify(home) +
      "))",
    "ribbon.APP_DIR = pathlib.Path(" + JSON.stringify(appDir) + ")",
    "root = ribbon.default_root()",
    "print(json.dumps(None if root is None else str(root)))"
  ])
  return JSON.parse(output)
}

function refusedPaths(paths) {
  const output = runPython([
    "import json, pathlib, ribbon",
    "print(json.dumps([p for p in " +
      JSON.stringify(paths) +
      " if not ribbon.is_safe_default_root(pathlib.Path(p))]))"
  ])
  return JSON.parse(output)
}

function tree(t) {
  const base = mkdtempSync(join(tmpdir(), "ribbon-root-"))
  t.after(() => rmSync(base, { recursive: true, force: true }))
  return join(base, "home")
}

test("a ribbon copied into the home folder is not guessed as the root", (t) => {
  const home = tree(t)
  for (const name of [ "bin", "docs", "photos" ]) {
    mkdirSync(join(home, name), { recursive: true })
  }
  assert.equal(defaultRootFor(home, home), null)
})

test("a ribbon in a home subfolder does not climb to the home folder", (t) => {
  const home = tree(t)
  const app = join(home, "bin")
  mkdirSync(app, { recursive: true })
  for (const name of [ "docs", "photos" ]) {
    mkdirSync(join(home, name), { recursive: true })
  }
  assert.equal(defaultRootFor(app, home), null)
})

test("a wrapper folder beside only the ribbon does not climb to home", (t) => {
  const home = tree(t)
  const work = join(home, "Work")
  mkdirSync(join(work, "_ribbon"), { recursive: true })
  mkdirSync(join(home, "docs"), { recursive: true })
  assert.equal(defaultRootFor(join(work, "_ribbon"), home), null)
})

test("a single projects container beside the ribbon is still found", (t) => {
  const home = tree(t)
  const work = join(home, "Work")
  mkdirSync(join(work, "_ribbon"), { recursive: true })
  mkdirSync(join(work, "tries", "one"), { recursive: true })
  assert.equal(defaultRootFor(join(work, "_ribbon"), home), join(work, "tries"))
})

test("projects sitting beside the ribbon are still found", (t) => {
  const home = tree(t)
  const work = join(home, "Work")
  mkdirSync(join(work, "_ribbon"), { recursive: true })
  mkdirSync(join(work, "alpha"), { recursive: true })
  mkdirSync(join(work, "beta"), { recursive: true })
  assert.equal(defaultRootFor(join(work, "_ribbon"), home), work)
})

test("the guard refuses the filesystem root, home, and system folders", () => {
  const refused = refusedPaths([
    "/",
    "/home",
    "/root",
    "/opt",
    "/usr",
    "/usr/local/bin",
    "/etc",
    "/var"
  ])
  for (const path of [
    "/",
    "/home",
    "/root",
    "/opt",
    "/usr",
    "/usr/local/bin",
    "/etc",
    "/var"
  ]) {
    assert.ok(refused.includes(path), path + " should not be guessed as a root")
  }
})

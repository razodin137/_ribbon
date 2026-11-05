import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import vm from "node:vm"

// bar.js is a classic script, not a module, so run it in a small sandbox with
// just the globals the pure layer needs. createBar is defined but not called.
const root = dirname(dirname(fileURLToPath(import.meta.url)))
const source = readFileSync(join(root, "bar.js"), "utf8")
const sandbox = { window: {} }
vm.runInNewContext(source, sandbox, { filename: "bar.js" })
const bar = sandbox.window.__RIBBON_BAR__

test("exposes the pure layer", () => {
  const names = [
    "appKey", "pad", "matchesQuery", "escapeAttribute", "defaultRepoName",
    "gitLights", "gitWorkRank", "decideGitAction", "repoTip", "changesTip",
    "remoteTip", "isParked"
  ]
  for (const name of names) {
    assert.equal(typeof bar[name], "function", name + " is missing")
  }
})

test("appKey prefers dir, then path, then url", () => {
  assert.equal(bar.appKey({ dir: "d", path: "p", url: "u" }), "d")
  assert.equal(bar.appKey({ path: "p", url: "u" }), "p")
  assert.equal(bar.appKey({ url: "u" }), "u")
  assert.equal(bar.appKey(null), "")
})

test("pad matches the width of the total", () => {
  assert.equal(bar.pad(1, 12), "01")
  assert.equal(bar.pad(1, 2), "1")
  assert.equal(bar.pad(9, 9), "9")
  assert.equal(bar.pad(10, 9), "10")
  assert.equal(bar.pad(1, 100), "001")
})

test("matchesQuery searches title, path, and type", () => {
  const app = { title: "Alpha", path: "2026-alpha", type: "HTML" }
  assert.equal(bar.matchesQuery(app, "alpha"), true)
  assert.equal(bar.matchesQuery({ title: "X", path: "2026-beta" }, "beta"), true)
  assert.equal(bar.matchesQuery(app, "html"), true)
  assert.equal(bar.matchesQuery(app, "zzz"), false)
  assert.equal(bar.matchesQuery(app, ""), true)
})

test("escapeAttribute neutralises markup", () => {
  assert.equal(
    bar.escapeAttribute("<a href=\"x\">&'"),
    "&lt;a href=&quot;x&quot;&gt;&amp;&#39;"
  )
  assert.equal(bar.escapeAttribute(null), "")
})

test("defaultRepoName strips the date and extension, then slugs", () => {
  assert.equal(bar.defaultRepoName({ path: "2026-11-02-foo-bar" }), "foo-bar")
  assert.equal(bar.defaultRepoName({ path: "Hello, World!" }), "hello-world")
  assert.equal(bar.defaultRepoName({}), "app")
  assert.equal(bar.defaultRepoName({ path: "x".repeat(200) }).length, 100)
})

test("gitLights turns state into three lights", () => {
  // Spread each vm-realm result into a local object so deepStrictEqual can
  // compare prototypes as well as values.
  assert.deepEqual({ ...bar.gitLights(null) }, {
    repo: false,
    dirty: false,
    count: 0,
    hasRemote: false,
    repoClass: "off",
    changesClass: "off",
    remoteClass: "off"
  })

  const clean = bar.gitLights({ repo: true, state: "clean", has_remote: true })
  assert.equal(clean.repoClass, "ok")
  assert.equal(clean.changesClass, "ok")
  assert.equal(clean.remoteClass, "ok")

  const dirty = bar.gitLights({
    repo: true,
    state: "dirty",
    dirty: true,
    dirty_count: 3,
    has_remote: true
  })
  assert.equal(dirty.changesClass, "warn")
  assert.equal(dirty.count, 3)

  const ahead = bar.gitLights({ repo: true, state: "ahead", ahead: 2, has_remote: true })
  assert.equal(ahead.remoteClass, "bad")

  const behind = bar.gitLights({ repo: true, state: "behind", has_remote: true })
  assert.equal(behind.remoteClass, "warn")

  const noRemote = bar.gitLights({ repo: true, state: "clean" })
  assert.equal(noRemote.remoteClass, "off")
})

test("gitWorkRank puts the most Git work first", () => {
  const rank = (git) => ({ ...bar.gitWorkRank({ git: git }) })
  assert.deepEqual(rank({ repo: true, state: "clean", has_remote: true }), { green: 3, severity: 0 })
  assert.deepEqual(rank({ repo: true, state: "dirty", dirty: true, has_remote: true }), { green: 2, severity: 1 })
  assert.deepEqual(rank({ repo: true, state: "ahead", has_remote: true }), { green: 2, severity: 2 })
  assert.deepEqual(rank({ repo: false }), { green: 0, severity: 9 })
})

test("decideGitAction picks one action per state", () => {
  assert.equal(bar.decideGitAction(null), "init")
  assert.equal(bar.decideGitAction({ repo: false }), "init")
  assert.equal(bar.decideGitAction({ repo: true, state: "conflicted" }), "info")

  const dirty = { repo: true, state: "dirty", files: [ "a" ], has_remote: true }
  assert.equal(bar.decideGitAction(dirty, "changes"), "commit")
  assert.equal(bar.decideGitAction(dirty), "commit")

  assert.equal(
    bar.decideGitAction({ repo: true, state: "dirty", files: [ "a" ], has_remote: false }, "remote"),
    "remote"
  )
  assert.equal(
    bar.decideGitAction({ repo: true, state: "no-commits", files: [], has_remote: false }, "remote"),
    "info"
  )
  assert.equal(
    bar.decideGitAction({ repo: true, state: "ahead", files: [], has_remote: true, ahead: 2 }, "remote"),
    "push"
  )
  assert.equal(
    bar.decideGitAction({
      repo: true,
      state: "clean",
      files: [],
      has_remote: true,
      upstream: "origin/main",
      remote_url: "git@github.com:me/app.git"
    }, "remote"),
    "pages"
  )
  assert.equal(
    bar.decideGitAction({ repo: true, state: "clean", files: [], has_remote: false }),
    "remote"
  )
  assert.equal(
    bar.decideGitAction({
      repo: true,
      state: "clean",
      files: [],
      has_remote: true,
      upstream: "origin/main",
      ahead: 0
    }),
    "info"
  )
})

test("tips describe the three lights", () => {
  assert.equal(bar.repoTip(null), "Not a Git repository")
  assert.equal(bar.repoTip({ state: "error" }), "Git status unavailable")
  assert.equal(bar.repoTip({ repo: true, branch: "main" }), "Git repository — main")

  assert.equal(bar.changesTip(null), "No changes to track")
  assert.equal(bar.changesTip({ repo: true }, true, 3), "3 uncommitted files")
  assert.equal(bar.changesTip({ repo: true }, true, 1), "1 uncommitted file")
  assert.equal(bar.changesTip({ repo: true, state: "no-commits" }), "No commits yet")
  assert.equal(bar.changesTip({ repo: true, state: "clean" }), "No uncommitted changes")

  assert.equal(bar.remoteTip(null), "No remote")
  assert.equal(bar.remoteTip({ repo: true }), "No remote")
  assert.equal(bar.remoteTip({ repo: true, state: "conflicted" }, true), "Conflicts to resolve")
  assert.equal(
    bar.remoteTip({ repo: true, state: "ahead", ahead: 2, behind: 1 }, true),
    "2 to push · 1 behind"
  )
  assert.equal(
    bar.remoteTip({ repo: true, state: "no-upstream" }, true),
    "Remote set, no upstream"
  )
  assert.equal(
    bar.remoteTip({ repo: true, state: "clean", upstream: "origin/main" }, true),
    "Up to date with origin/main"
  )
})

test("isParked respects the snooze date", () => {
  const future = new Date(Date.now() + 86400000).toISOString()
  const past = new Date(Date.now() - 86400000).toISOString()
  assert.equal(bar.isParked({ parked_until: future }), true)
  assert.equal(bar.isParked({ parked_until: past }), false)
  assert.equal(bar.isParked({}), false)
  assert.equal(bar.isParked({ parked_until: "not-a-date" }), false)
})

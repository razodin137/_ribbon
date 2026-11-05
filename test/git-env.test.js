import assert from "node:assert/strict"
import { execFileSync } from "node:child_process"
import { mkdtempSync, mkdirSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"
import process from "node:process"
import test from "node:test"
import { fileURLToPath } from "node:url"

// Git reads repo-selection variables from the environment before it looks at
// -C, so a shell that exports GIT_DIR must not redirect Ribbon's status and
// commit commands at another repository.
const root = dirname(dirname(fileURLToPath(import.meta.url)))

const script = String.raw`
import json, sys
from pathlib import Path
import ribbon

outside = Path(sys.argv[1])
print(json.dumps({
    "status": ribbon.read_git_status(outside),
    "toplevel": ribbon._git_text(outside, ["rev-parse", "--show-toplevel"]),
    "env": ribbon._git_env(),
}))
`

const run = (cwd, env) =>
  JSON.parse(
    execFileSync("python3", [ "-c", script, cwd ], {
      cwd: root,
      env: { ...process.env, ...env },
      encoding: "utf8"
    })
  )

const poisoned = (repo) => ({
  GIT_DIR: join(repo, ".git"),
  GIT_WORK_TREE: repo,
  GIT_INDEX_FILE: join(repo, ".git", "index"),
  GIT_COMMON_DIR: join(repo, ".git"),
  GIT_OBJECT_DIRECTORY: join(repo, ".git", "objects"),
  GIT_NAMESPACE: "elsewhere"
})

test("an inherited GIT_DIR does not point git at another repository", () => {
  const work = mkdtempSync(join(tmpdir(), "ribbon-git-env-"))
  try {
    const repo = join(work, "repo")
    const outside = join(work, "outside")
    mkdirSync(repo)
    mkdirSync(outside)
    execFileSync("git", [ "init", "-q", repo ])

    const clean = run(outside, {})
    assert.equal(clean.status.repo, false)
    assert.equal(clean.toplevel, "")

    const leaked = run(outside, poisoned(repo))
    assert.equal(leaked.status.repo, false)
    assert.equal(leaked.toplevel, "")
    for (const name of Object.keys(poisoned(repo))) {
      assert.equal(leaked.env[name], undefined, name + " reached the git env")
    }

    const local = run(repo, { GIT_DIR: join(work, "nowhere") })
    assert.equal(local.status.repo, true, "a real repo still resolves")
  } finally {
    rmSync(work, { recursive: true, force: true })
  }
})

test("prompting stays off and the ignore check uses the same env", () => {
  const env = run(root, { GIT_DIR: join(root, ".git") })
  assert.equal(env.env.GIT_TERMINAL_PROMPT, "0")

  const source = execFileSync(
    "python3",
    [
      "-c",
      "import inspect, ribbon; print(inspect.getsource(ribbon._git_check_ignored))"
    ],
    { cwd: root, encoding: "utf8" }
  )
  assert.match(source, /env=_git_env\(\)/)
})

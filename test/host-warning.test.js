import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import test, { after, before } from "node:test"
import { fileURLToPath } from "node:url"

// --host on a non-local address keeps writes off, but reads stay open and
// unauthenticated. The startup banner is the only warning, so it must say
// plainly that anyone on the network can read the projects.

const project = dirname(dirname(fileURLToPath(import.meta.url)))
const scratch = mkdtempSync(join(project, ".scratch-host-"))
const root = join(scratch, "root")

let server = null
let output = ""

function start() {
  mkdirSync(join(root, "app"), { recursive: true })
  writeFileSync(
    join(root, "app", "index.html"),
    "<!doctype html><title>app</title>\n"
  )

  const child = spawn(
    "python3",
    [
      "-u",
      "ribbon.py",
      "--root",
      root,
      "--host",
      "0.0.0.0",
      "--port",
      "0",
      "--no-open",
      "--no-git-actions"
    ],
    { cwd: project, stdio: [ "ignore", "pipe", "pipe" ] }
  )

  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`server did not start:\n${output}`)),
      10000
    )
    const read = (chunk) => {
      output += chunk
      if (/open\s+http:\/\//.test(output)) {
        clearTimeout(timer)
        resolve(child)
      }
    }
    child.stdout.setEncoding("utf8")
    child.stdout.on("data", read)
    child.stderr.setEncoding("utf8")
    child.stderr.on("data", (chunk) => {
      output += chunk
    })
    child.on("exit", (code) => {
      clearTimeout(timer)
      reject(new Error(`server exited with ${code}:\n${output}`))
    })
  })
}

before(async () => {
  server = await start()
})

after(() => {
  if (server) server.kill()
  rmSync(scratch, { recursive: true, force: true })
})

test("a network bind says that reads have no password", () => {
  assert.match(output, /WARNING: Ribbon is listening beyond this computer/)
  assert.match(output, /can read every project/)
  assert.match(output, /There is no password/)
  assert.match(output, /Git actions, deletes, and saved state\s+stay off/)
})

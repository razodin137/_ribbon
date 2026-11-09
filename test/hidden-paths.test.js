import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import { mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { request } from "node:http"
import { dirname, join } from "node:path"
import test, { after, before } from "node:test"
import { fileURLToPath } from "node:url"

// Ribbon serves a folder of apps. It must never hand out a dot entry: .git
// carries cloneable history and remote URLs, and .env carries secrets. These
// checks run against a real server, because translate_path() does the decoding
// and only a request can prove the path never reaches it.
//
// Every check below looks at a status code. No file body is printed.

const project = dirname(dirname(fileURLToPath(import.meta.url)))
const scratch = mkdtempSync(join(project, ".scratch-hidden-"))
const root = join(scratch, "root")

let server = null
let port = 0

function write(path, text) {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, text)
}

function status(path, method = "GET") {
  return new Promise((resolve, reject) => {
    const req = request({ host: "127.0.0.1", port, path, method }, (res) => {
      res.resume()
      res.on("end", () => resolve(res.statusCode))
    })
    req.on("error", reject)
    req.end()
  })
}

function makeRoot() {
  write(join(root, "app", "index.html"), "<!doctype html><title>app</title>\n")
  write(join(root, "proj", "data.json"), "{}\n")
  write(join(root, "notes", "README.md"), "# Notes\n")
  write(join(root, ".git", "config"), "[core]\n\trepositoryformatversion = 0\n")
  write(join(root, ".git", "HEAD"), "ref: refs/heads/main\n")
  write(join(root, ".env"), "SECRET=not-a-real-secret\n")
  write(join(root, "proj", ".env"), "SECRET=not-a-real-secret\n")
  symlinkSync(join(root, "app"), join(root, "app-link"))
  symlinkSync("/etc/passwd", join(root, "link.txt"))
  symlinkSync("/etc", join(root, "etc-link"))
}

function start() {
  const child = spawn(
    "python3",
    [
      "-u",
      "ribbon.py",
      "--root",
      root,
      "--port",
      "0",
      "--no-open",
      "--no-git-actions"
    ],
    { cwd: project, stdio: [ "ignore", "pipe", "pipe" ] }
  )

  return new Promise((resolve, reject) => {
    let output = ""
    const timer = setTimeout(
      () => reject(new Error(`server did not start:\n${output}`)),
      10000
    )
    child.stdout.setEncoding("utf8")
    child.stdout.on("data", (chunk) => {
      output += chunk
      const found = output.match(/open\s+http:\/\/127\.0\.0\.1:(\d+)\//)
      if (found) {
        clearTimeout(timer)
        resolve({ child, port: Number(found[1]) })
      }
    })
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
  makeRoot()
  const started = await start()
  server = started.child
  port = started.port
})

after(() => {
  if (server) server.kill()
  rmSync(scratch, { recursive: true, force: true })
})

test("dot entries are never served", async () => {
  for (const path of [
    "/.git/config",
    "/.git/HEAD",
    "/.git/",
    "/.env",
    "/proj/.env",
    "/.gitignore"
  ]) {
    assert.equal(await status(path), 404, path)
  }
})

test("an encoded dot does not slip past", async () => {
  assert.equal(await status("/%2egit/config"), 404)
  assert.equal(await status("/%2eenv"), 404)
})

test("a HEAD request is refused too", async () => {
  assert.equal(await status("/.env", "HEAD"), 404)
  assert.equal(await status("/.git/config", "HEAD"), 404)
})

test("the card route cannot list a dot folder", async () => {
  assert.equal(await status("/__ribbon/card/.git/"), 404)
  assert.equal(await status("/__ribbon/card/.git"), 404)
})

test("a symlink cannot lead outside the root", async () => {
  assert.equal(await status("/link.txt"), 404)
  assert.equal(await status("/etc-link/passwd"), 404)
})

test("normal pages and in-root symlinks still work", async () => {
  assert.equal(await status("/app/"), 200)
  assert.equal(await status("/app/index.html"), 200)
  assert.equal(await status("/app-link/"), 200)
  assert.equal(await status("/__ribbon/card/proj"), 200)
})

test("a markdown project still has an overview card", async () => {
  assert.equal(await status("/__ribbon/card/notes/"), 200)
})

/* Ribbon Shelf — the new tab pane.
 *
 * Ribbon serves a manifest at /__ribbon/manifest.json on the first free port
 * from 8765 upward, so look in that window instead of assuming one port.
 */
(function () {
  "use strict"

  const START_PORT = 8765
  const PORT_COUNT = 20
  const PROBE_TIMEOUT_MS = 800
  const HOSTS = [ "127.0.0.1", "localhost", "[::1]" ]
  const DESCRIPTION_LIMIT = 150
  const STATE_LABELS = {
    clean: "all pushed",
    dirty: "unsaved changes",
    ahead: "commits to push",
    behind: "behind the remote",
    diverged: "ahead and behind",
    "no-upstream": "not linked to a remote",
    "no-commits": "no commits yet",
    detached: "detached HEAD",
    conflicted: "conflicts to resolve",
    "no-repo": "no git",
    error: "git unavailable"
  }
  const STATE_TONES = {
    clean: "ok",
    dirty: "warn",
    ahead: "bad",
    behind: "warn",
    diverged: "bad",
    "no-upstream": "warn",
    "no-commits": "warn",
    detached: "warn",
    conflicted: "bad",
    "no-repo": "off",
    error: "off"
  }

  const loadingEl = document.getElementById("loading")
  const noticeEl = document.getElementById("notice")
  const noticeTitleEl = document.getElementById("notice-title")
  const noticeTextEl = document.getElementById("notice-text")
  const commandEl = document.getElementById("notice-command")
  const retryEl = document.getElementById("retry")
  const shelfEl = document.getElementById("shelf")

  let busy = false

  function probe(host, port) {
    const controller = new AbortController()
    const timer = setTimeout(function () {
      controller.abort()
    }, PROBE_TIMEOUT_MS)

    return fetch(`http://${host}:${port}/__ribbon/manifest.json`, {
      cache: "no-store",
      signal: controller.signal
    })
      .then(function (response) {
        if (!response.ok) return null
        return response.json()
      })
      .then(function (data) {
        if (!data || !Array.isArray(data.apps)) return null
        return { base: `http://${host}:${port}`, apps: data.apps }
      })
      .catch(function () {
        return null
      })
      .finally(function () {
        clearTimeout(timer)
      })
  }

  function scanHost(host) {
    const ports = []
    for (let port = START_PORT; port < START_PORT + PORT_COUNT; port++) {
      ports.push(port)
    }
    return Promise.all(ports.map(function (port) {
      return probe(host, port)
    })).then(function (results) {
      return results.find(function (result) {
        return result !== null
      }) || null
    })
  }

  async function findRibbon() {
    for (const host of HOSTS) {
      const found = await scanHost(host)
      if (found) return found
    }
    return null
  }

  function shorten(text) {
    if (text.length <= DESCRIPTION_LIMIT) return text
    return text.slice(0, DESCRIPTION_LIMIT - 1).trimEnd() + "…"
  }

  function stateWord(tone, label) {
    const item = document.createElement("span")
    item.className = "git-state"
    const dot = document.createElement("span")
    dot.className = "git-dot " + tone
    dot.setAttribute("aria-hidden", "true")
    const text = document.createElement("span")
    text.textContent = label
    item.append(dot, text)
    return item
  }

  function gitState(git) {
    if (!git || typeof git !== "object") return null
    const state = typeof git.state === "string" ? git.state : ""
    const label = STATE_LABELS[state] || state
    if (!label) return null

    const status = document.createElement("span")
    status.className = "status"
    status.append(stateWord(STATE_TONES[state] || "off", label))
    if (git.dirty && state !== "dirty") {
      status.append(stateWord("warn", STATE_LABELS.dirty))
    }
    return status
  }

  function projectCard(app, base) {
    const title = typeof app.title === "string" && app.title ? app.title : "Untitled"
    const type = typeof app.type === "string" && app.type ? app.type : "Folder"
    let href
    try {
      href = new URL(app.url || "/", base + "/")
    } catch (_) {
      return null
    }
    if (href.protocol !== "http:" && href.protocol !== "https:") return null

    const card = document.createElement("a")
    card.className = "card"
    card.href = href.href
    card.setAttribute("aria-label", `${title}, ${type}`)

    const color = typeof app.color === "string" ? app.color : ""
    if (color && CSS.supports("color", color)) {
      card.style.setProperty("--accent", color)
    }

    const top = document.createElement("span")
    top.className = "card-top"
    const swatch = document.createElement("span")
    swatch.className = "swatch"
    swatch.setAttribute("aria-hidden", "true")
    const typeLabel = document.createElement("span")
    typeLabel.className = "type"
    typeLabel.textContent = type
    top.append(swatch, typeLabel)

    const name = document.createElement("span")
    name.className = "name"
    name.textContent = title

    card.append(top, name)

    const description = typeof app.description === "string" ? app.description.trim() : ""
    if (description) {
      const desc = document.createElement("span")
      desc.className = "desc"
      desc.textContent = shorten(description)
      card.append(desc)
    }

    const status = gitState(app.git)
    if (status) card.append(status)

    const open = document.createElement("span")
    open.className = "open"
    open.setAttribute("aria-hidden", "true")
    open.textContent = "Open"
    const arrow = document.createElement("span")
    arrow.className = "arrow"
    arrow.textContent = "→"
    open.append(arrow)
    card.append(open)

    return card
  }

  function showLoading() {
    loadingEl.hidden = false
    noticeEl.hidden = true
    shelfEl.hidden = true
    retryEl.hidden = true
  }

  function showNotice(title, text, withCommand) {
    loadingEl.hidden = true
    shelfEl.hidden = true
    noticeEl.hidden = false
    retryEl.hidden = false
    noticeTitleEl.textContent = title
    noticeTextEl.textContent = text
    commandEl.hidden = !withCommand
  }

  function showShelf(apps, base) {
    loadingEl.hidden = true
    noticeEl.hidden = true
    retryEl.hidden = true

    if (!apps.length) {
      showNotice("Ribbon is running.", "It has no projects to show yet.", false)
      return
    }

    const cards = []
    for (const app of apps) {
      const card = projectCard(app, base)
      if (card) cards.push(card)
    }

    if (!cards.length) {
      showNotice("Ribbon is running.", "It has no projects to show yet.", false)
      return
    }

    shelfEl.replaceChildren(...cards)
    shelfEl.hidden = false
  }

  async function detect() {
    if (busy) return
    busy = true
    showLoading()

    try {
      const found = await findRibbon()
      if (found) {
        showShelf(found.apps, found.base)
      } else {
        showNotice(
          "Ribbon is not running.",
          "Start Ribbon in a terminal and keep the window open, then check again.",
          true
        )
      }
    } finally {
      busy = false
    }
  }

  retryEl.addEventListener("click", detect)
  detect()
})()

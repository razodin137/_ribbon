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
  const CACHE_KEY = "ribbon.newtab"
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
  const SORT_KEY = "ribbon.newtab.sort"
  const SORT_MODES = [ "status", "type", "name" ]
  // How much work a repo still needs. Highest first, so a conflicted repo sits
  // above a clean one. The words and tones match the bar's gitLights().
  const STATE_WORK = {
    conflicted: 9,
    diverged: 8,
    ahead: 7,
    dirty: 6,
    behind: 5,
    detached: 4,
    "no-upstream": 4,
    "no-commits": 3,
    error: 2,
    "no-repo": 1,
    clean: 0
  }

  const loadingEl = document.getElementById("loading")
  const noticeEl = document.getElementById("notice")
  const noticeTitleEl = document.getElementById("notice-title")
  const noticeTextEl = document.getElementById("notice-text")
  const commandEl = document.getElementById("notice-command")
  const retryEl = document.getElementById("retry")
  const sortEl = document.getElementById("sortbar")
  const sortButtons = Array.from(document.querySelectorAll(".sort-option"))
  const shelfEl = document.getElementById("shelf")

  let busy = false
  let shown = null
  let sortMode = readSort()

  function normalizeBase(value) {
    try {
      const url = new URL(value)
      if (url.protocol !== "http:" && url.protocol !== "https:") return null
      if (!HOSTS.includes(url.hostname)) return null
      return url.origin
    } catch (_) {
      return null
    }
  }

  function readCache() {
    try {
      const data = JSON.parse(localStorage.getItem(CACHE_KEY) || "null")
      if (!data || typeof data !== "object") return null
      const base = normalizeBase(data.base)
      if (!base) return null
      const apps = Array.isArray(data.apps) ? data.apps : []
      return { base: base, apps: apps }
    } catch (_) {
      return null
    }
  }

  function writeCache(found) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({ base: found.base, apps: found.apps }))
    } catch (_) {
      return
    }
  }

  function dropCache() {
    try {
      localStorage.removeItem(CACHE_KEY)
    } catch (_) {
      return
    }
  }

  function isSortMode(value) {
    return SORT_MODES.includes(value)
  }

  function readSort() {
    try {
      const value = localStorage.getItem(SORT_KEY)
      return isSortMode(value) ? value : "status"
    } catch (_) {
      return "status"
    }
  }

  function writeSort(mode) {
    try {
      localStorage.setItem(SORT_KEY, mode)
    } catch (_) {
      return
    }
  }

  function nameOf(app) {
    return typeof app.title === "string" && app.title ? app.title : "Untitled"
  }

  function typeOf(app) {
    return typeof app.type === "string" && app.type ? app.type : "Folder"
  }

  function statusWork(app) {
    const git = app && app.git
    if (!git || typeof git !== "object") return -1
    const state = typeof git.state === "string" ? git.state : ""
    let work = STATE_WORK[state] || 0
    if (git.dirty && state !== "dirty") work += 0.5
    return work
  }

  function compareApps(a, b, mode) {
    if (mode === "status") {
      const workA = statusWork(a)
      const workB = statusWork(b)
      if (workA !== workB) return workB - workA
    } else if (mode === "type") {
      const typeA = typeOf(a)
      const typeB = typeOf(b)
      if (typeA !== typeB) return typeA.localeCompare(typeB)
    }
    return nameOf(a).localeCompare(nameOf(b))
  }

  function sortApps(apps, mode) {
    return apps.slice().sort(function (a, b) {
      return compareApps(a, b, mode)
    })
  }

  function syncSort() {
    for (const button of sortButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.sort === sortMode))
    }
  }

  function loadManifest(base) {
    const controller = new AbortController()
    const timer = setTimeout(function () {
      controller.abort()
    }, PROBE_TIMEOUT_MS)

    return fetch(`${base}/__ribbon/manifest.json`, {
      cache: "no-store",
      signal: controller.signal
    })
      .then(function (response) {
        if (!response.ok) return null
        return response.json()
      })
      .then(function (data) {
        if (!data || !Array.isArray(data.apps)) return null
        return { base: base, apps: data.apps }
      })
      .catch(function () {
        return null
      })
      .finally(function () {
        clearTimeout(timer)
      })
  }

  const BAR_ROUTE = "/__ribbon/bar.html"
  let barBase = null

  // The real bar lives beside the server's assets. Fetch the same shell a
  // served page gets, then load the extension's copies of bar.js and
  // ribbon.js, pointed back at this Ribbon so app links resolve to it.
  function installBar(base) {
    if (barBase === base) return
    barBase = base
    fetch(`${base}${BAR_ROUTE}`, { cache: "no-cache" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status)
        return response.text()
      })
      .then(function (html) {
        if (document.querySelector("[data-ribbon-host]")) return
        document.body.insertAdjacentHTML("afterbegin", html)
        const barScript = document.createElement("script")
        barScript.src = "bar.js"
        barScript.addEventListener("load", function () {
          const ribbonScript = document.createElement("script")
          ribbonScript.src = "ribbon.js"
          ribbonScript.setAttribute("data-ribbon-base", base)
          ribbonScript.setAttribute("data-ribbon-title", "home")
          ribbonScript.setAttribute(
            "data-ribbon-home",
            globalThis.chrome.runtime.getURL("newtab.html")
          )
          document.head.appendChild(ribbonScript)
        })
        document.head.appendChild(barScript)
      })
      .catch(function () {
        barBase = null
      })
  }

  function scanHost(host) {
    const ports = []
    for (let port = START_PORT; port < START_PORT + PORT_COUNT; port++) {
      ports.push(port)
    }
    return Promise.all(ports.map(function (port) {
      return loadManifest(`http://${host}:${port}`)
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
    const title = nameOf(app)
    const type = typeOf(app)
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
    sortEl.hidden = true
    retryEl.hidden = true
    shown = null
  }

  function showNotice(title, text, withCommand) {
    loadingEl.hidden = true
    shelfEl.hidden = true
    sortEl.hidden = true
    noticeEl.hidden = false
    retryEl.hidden = false
    noticeTitleEl.textContent = title
    noticeTextEl.textContent = text
    commandEl.hidden = !withCommand
    shown = null
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
    for (const app of sortApps(apps, sortMode)) {
      const card = projectCard(app, base)
      if (card) cards.push(card)
    }

    if (!cards.length) {
      showNotice("Ribbon is running.", "It has no projects to show yet.", false)
      return
    }

    shown = { apps: apps, base: base }
    syncSort()
    sortEl.hidden = false
    shelfEl.replaceChildren(...cards)
    shelfEl.hidden = false
  }

  function setSort(mode) {
    if (!isSortMode(mode)) return
    sortMode = mode
    writeSort(mode)
    syncSort()
    if (shown) showShelf(shown.apps, shown.base)
  }

  async function detect() {
    if (busy) return
    busy = true

    const cached = readCache()
    if (cached) {
      showShelf(cached.apps, cached.base)
    } else {
      showLoading()
    }

    try {
      let found = null
      if (cached) found = await loadManifest(cached.base)
      if (!found) found = await findRibbon()

      if (found) {
        writeCache(found)
        installBar(found.base)
        showShelf(found.apps, found.base)
      } else {
        dropCache()
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

  for (const button of sortButtons) {
    button.addEventListener("click", function () {
      setSort(button.dataset.sort)
    })
  }

  retryEl.addEventListener("click", detect)
  detect()
})()

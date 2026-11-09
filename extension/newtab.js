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
  const CARD_ROUTE = "/__ribbon/card/"
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
  const overviewEl = document.getElementById("overview")
  const overviewCloseEl = document.getElementById("overview-close")
  const overviewFrame = document.getElementById("overview-frame")

  let busy = false
  let shown = null
  let sortMode = readSort()
  let overviewTrigger = null

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

  // Mirrors gitLights() in bar.js, so a card shows the same three dots as the
  // bar: repository, changes, remote.
  function gitLights(git) {
    const repo = !!(git && git.repo)
    const state = (git && git.state) || ""
    const dirty = !!(git && (git.dirty || (git.files && git.files.length)))
    const count = git && typeof git.dirty_count === "number" ? git.dirty_count : dirty ? 1 : 0
    const hasRemote = !!(git && git.has_remote)
    let remoteClass = "off"
    if (repo && hasRemote) {
      if (state === "ahead" || state === "diverged" || state === "conflicted") {
        remoteClass = "bad"
      } else if (
        state === "behind" ||
        state === "no-upstream" ||
        state === "detached" ||
        state === "no-commits"
      ) {
        remoteClass = "warn"
      } else {
        remoteClass = "ok"
      }
    }
    return {
      repo: repo,
      dirty: dirty,
      count: count,
      hasRemote: hasRemote,
      repoClass: repo ? "ok" : "off",
      changesClass: !repo ? "off" : dirty ? "warn" : "ok",
      remoteClass: remoteClass
    }
  }

  function repoTip(git) {
    if (!git || !git.repo) {
      return git && git.state === "error"
        ? "Git status unavailable"
        : "Not a Git repository"
    }
    return "Git repository" + (git.branch ? " — " + git.branch : "")
  }

  function changesTip(git, dirty, count) {
    if (!git || !git.repo) return "No changes to track"
    if (dirty) {
      const n = count || 1
      return n + " uncommitted file" + (n === 1 ? "" : "s")
    }
    return git.state === "no-commits" ? "No commits yet" : "No uncommitted changes"
  }

  function remoteTip(git, hasRemote) {
    if (!git || !git.repo) return "No remote"
    if (!hasRemote) return "No remote"
    if (git.state === "conflicted") return "Conflicts to resolve"
    if (git.state === "no-commits") return "No commits yet"
    if (git.state === "detached") return "Detached HEAD"
    const bits = []
    if (git.ahead) bits.push(git.ahead + " to push")
    if (git.behind) bits.push(git.behind + " behind")
    if (bits.length) return bits.join(" · ")
    if (git.state === "no-upstream") return "Remote set, no upstream"
    return "Up to date" + (git.upstream ? " with " + git.upstream : "")
  }

  function gitDot(tone, tip) {
    const dot = document.createElement("span")
    dot.className = "git-dot " + tone
    dot.title = tip
    dot.setAttribute("aria-hidden", "true")
    return dot
  }

  function gitState(git) {
    if (!git || typeof git !== "object") return null
    const state = typeof git.state === "string" ? git.state : ""
    const label = STATE_LABELS[state] || state
    if (!label) return null

    const lights = gitLights(git)
    const status = document.createElement("span")
    status.className = "status"

    const dots = document.createElement("span")
    dots.className = "git-lights"
    dots.append(
      gitDot(lights.repoClass, repoTip(git)),
      gitDot(lights.changesClass, changesTip(git, lights.dirty, lights.count)),
      gitDot(lights.remoteClass, remoteTip(git, lights.hasRemote))
    )

    const summary = document.createElement("span")
    summary.className = "git-summary"
    summary.textContent = label

    status.append(dots, summary)
    return status
  }

  function overviewUrl(app, base) {
    const rel = typeof app.path === "string" ? app.path.replace(/^\/+|\/+$/g, "") : ""
    if (!rel) return ""
    const parts = rel.split("/").map(encodeURIComponent)
    return `${base}${CARD_ROUTE}${parts.join("/")}/?embed=1`
  }

  function openOverview(app, base) {
    const url = overviewUrl(app, base)
    if (!url) return
    overviewTrigger = document.activeElement
    const title = nameOf(app)
    overviewEl.setAttribute("aria-label", "Overview of " + title)
    overviewFrame.title = "Overview of " + title
    overviewFrame.style.height = "320px"
    overviewFrame.src = url
    if (!overviewEl.open) overviewEl.showModal()
  }

  function closeOverview() {
    if (overviewEl.open) overviewEl.close()
  }

  function overviewButton(app, base) {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "card-overview"
    button.setAttribute("aria-label", "Overview of " + nameOf(app))
    button.title = "Overview"
    button.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>' +
      '<rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>'
    button.addEventListener("click", function () {
      openOverview(app, base)
    })
    return button
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

    const shell = document.createElement("div")
    shell.className = "card-shell"
    shell.append(card)
    if (overviewUrl(app, base)) shell.append(overviewButton(app, base))
    return shell
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

  overviewCloseEl.addEventListener("click", closeOverview)
  overviewEl.addEventListener("click", function (event) {
    if (event.target === overviewEl) closeOverview()
  })
  overviewEl.addEventListener("close", function () {
    overviewFrame.src = "about:blank"
    overviewFrame.style.removeProperty("height")
    if (overviewTrigger && typeof overviewTrigger.focus === "function") {
      overviewTrigger.focus()
    }
    overviewTrigger = null
  })
  window.addEventListener("message", function (event) {
    if (!overviewEl.open) return
    if (!overviewFrame.contentWindow || event.source !== overviewFrame.contentWindow) return
    const data = event.data
    if (!data || data.type !== "ribbon-card-size") return
    const height = Number(data.height)
    if (!Number.isFinite(height) || height <= 0) return
    overviewFrame.style.height = Math.ceil(height) + "px"
  })

  for (const button of sortButtons) {
    button.addEventListener("click", function () {
      setSort(button.dataset.sort)
    })
  }

  retryEl.addEventListener("click", detect)
  detect()
})()

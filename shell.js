(function () {
  "use strict"

  const apps = (Array.isArray(window.__RIBBON_APPS__) ? window.__RIBBON_APPS__ : []).filter(function (app) {
    return app && typeof app.url === "string" && app.url
  })

  const bar = document.getElementById("bar")
  const countEl = document.getElementById("count")
  const titleButton = document.getElementById("title")
  const titleText = document.getElementById("title-text")
  const frame = document.getElementById("app")
  const empty = document.getElementById("empty")
  const peek = document.getElementById("peek")
  const ledsWrap = document.getElementById("leds")
  const ledButtons = document.querySelectorAll(".led-btn")
  const ledWrap = ledsWrap.parentNode
  const ledTip = document.getElementById("led-tip")
  const tipRepoDot = ledTip.querySelector('[data-tip-led="repo"]')
  const tipChangesDot = ledTip.querySelector('[data-tip-led="changes"]')
  const tipRemoteDot = ledTip.querySelector('[data-tip-led="remote"]')
  const tipRepoText = ledTip.querySelector('[data-tip-text="repo"]')
  const tipChangesText = ledTip.querySelector('[data-tip-text="changes"]')
  const tipRemoteText = ledTip.querySelector('[data-tip-text="remote"]')
  const ledRepo = document.getElementById("led-repo")
  const ledChanges = document.getElementById("led-changes")
  const ledRemote = document.getElementById("led-remote")
  const buttons = document.querySelectorAll("button[data-act]")

  const gitOverlay = document.getElementById("git-overlay")
  const gitTitle = document.getElementById("git-title")
  const gitSummary = document.getElementById("git-summary")
  const gitFiles = document.getElementById("git-files")
  const gitWarnings = document.getElementById("git-warnings")
  const gitMessageField = document.getElementById("git-message-field")
  const gitMessage = document.getElementById("git-message")
  const gitNameField = document.getElementById("git-name-field")
  const gitName = document.getElementById("git-name")
  const gitVisibilityField = document.getElementById("git-visibility-field")
  const gitVisibilityInputs = document.querySelectorAll('input[name="git-visibility"]')
  const gitDescriptionField = document.getElementById("git-description-field")
  const gitDescription = document.getElementById("git-description")
  const gitReadmeField = document.getElementById("git-readme-field")
  const gitReadme = document.getElementById("git-readme")
  const gitPagesField = document.getElementById("git-pages-field")
  const gitPages = document.getElementById("git-pages")
  const gitIgnoreField = document.getElementById("git-ignore-field")
  const gitIgnore = document.getElementById("git-ignore")
  const gitNote = document.getElementById("git-note")
  const gitOutput = document.getElementById("git-output")
  const gitStatus = document.getElementById("git-status")
  const gitCancel = document.getElementById("git-cancel")
  const gitPrimary = document.getElementById("git-primary")
  const gitClose = document.getElementById("git-close")
  const gitSession = fetch("/__ribbon/manifest.json", { cache: "no-store" })
    .then(function (response) {
      return response.ok ? response.json() : null
    })
    .then(function (data) {
      return { token: (data && data.token) || "", write: !!(data && data.write) }
    })
    .catch(function () {
      return { token: "", write: false }
    })

  const menuEl = document.getElementById("menu")
  const menuCurrentTitle = document.getElementById("menu-current-title")
  const starTitle = document.getElementById("star-title")
  const starCurrent = document.getElementById("star-current")
  const starButtons = [ starTitle, starCurrent ]
  const searchInput = document.getElementById("menu-input")
  const menuFavSection = menuEl.querySelector('[data-section="favorites"]')
  const menuAllSection = menuEl.querySelector('[data-section="all"]')
  const menuFavList = menuEl.querySelector('[data-list="favorites"]')
  const menuAllList = menuEl.querySelector('[data-list="all"]')
  const menuAllHeading = menuAllSection.querySelector(".menu-heading")
  const menuEmpty = menuEl.querySelector(".menu-empty")

  const STORAGE_KEY = "ribbon:shell-hidden"
  let index = -1
  let manualHidden = readHidden()
  let autoHidden = false
  let suppressScrollUntil = 0
  const lastTargets = new Map()
  const wiredDocs = new WeakSet()
  let tipPinned = false
  let tipTimer = 0
  const hoverCapable = window.matchMedia("(hover: hover)").matches
  const favorites = readFavorites()
  let menuOpen = false
  let gitToken = ""
  let gitDetail = null
  let gitAction = null
  let gitBusy = false
  let gitBlocked = false
  let gitReturnFocus = null

  frame.addEventListener("load", wireFrame)

  if (!apps.length) {
    empty.hidden = false
    frame.hidden = true
    titleText.textContent = "No apps listed"
    titleButton.title = "Show all apps"
    menuCurrentTitle.textContent = "No apps listed"
    countEl.textContent = "00 / 00"
    disablePaging()
    setGit(null)
    updateCurrentStar()
    applyHidden()
  } else {
    let start = 0
    const hash = readHash()
    if (hash) {
      for (let i = 0; i < apps.length; i += 1) {
        if (appHash(apps[i]) === hash) {
          start = i
          break
        }
      }
    }
    setApp(start)
  }

  window.addEventListener("keydown", onKey, true)
  window.addEventListener("hashchange", function () {
    const wanted = readHash()
    if (!wanted) return
    for (let i = 0; i < apps.length; i += 1) {
      if (appHash(apps[i]) === wanted && i !== index) {
        setApp(i, false)
        break
      }
    }
  })

  bar.addEventListener("click", function (event) {
    const button = event.target && event.target.closest
      ? event.target.closest("button[data-act]")
      : null
    if (!button) return
    const action = button.getAttribute("data-act")
    if (action === "prev") step(-1)
    else if (action === "next") step(1)
    else if (action === "random") random()
    else if (action === "reload") reloadApp()
    else if (action === "hide") setManual(true)
  })

  peek.addEventListener("click", function () {
    setManual(false)
  })

  titleButton.addEventListener("click", toggleMenu)
  starTitle.addEventListener("click", function () {
    const app = currentApp()
    if (app) toggleFavorite(app, false)
    starTitle.focus()
  })
  starCurrent.addEventListener("click", function () {
    const app = currentApp()
    if (app) toggleFavorite(app, false)
    starCurrent.focus()
  })
  searchInput.addEventListener("input", function () {
    renderMenu(searchInput.value)
  })
  searchInput.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      event.preventDefault()
      closeMenu(true)
      return
    }
    if (event.key === "Enter") {
      const first = menuEl.querySelector(".menu-app")
      if (first) {
        event.preventDefault()
        setApp(Number(first.getAttribute("data-app")))
      }
      return
    }
    if (event.key === "ArrowDown") {
      const first = menuEl.querySelector(".menu-app")
      if (first) {
        event.preventDefault()
        first.focus()
      }
    }
  })
  menuEl.addEventListener("click", function (event) {
    const star = event.target && event.target.closest
      ? event.target.closest(".row-star")
      : null
    if (star) {
      for (let i = 0; i < apps.length; i += 1) {
        if (appKey(apps[i]) === star.getAttribute("data-star")) {
          toggleFavorite(apps[i], true)
          break
        }
      }
      return
    }

    const row = event.target && event.target.closest
      ? event.target.closest(".menu-app")
      : null
    if (row) setApp(Number(row.getAttribute("data-app")))
  })
  document.addEventListener("pointerdown", function (event) {
    if (!menuOpen) return
    if (bar.contains(event.target)) return
    closeMenu(false)
  }, true)

  ledsWrap.addEventListener("click", function (event) {
    const button = event.target && event.target.closest
      ? event.target.closest(".led-btn")
      : null
    if (!button) return
    event.stopPropagation()
    openGitPanel(button.getAttribute("data-led"))
  })
  ledsWrap.addEventListener("pointerenter", function () {
    if (hoverCapable) openTip(false)
  })
  ledsWrap.addEventListener("pointerleave", closeTipIfUnpinned)
  for (let b = 0; b < ledButtons.length; b += 1) {
    ledButtons[b].addEventListener("focus", function () {
      openTip(false)
    })
    ledButtons[b].addEventListener("blur", closeTipIfUnpinned)
  }

  gitCancel.addEventListener("click", closeGitPanel)
  gitClose.addEventListener("click", closeGitPanel)
  gitPrimary.addEventListener("click", submitGitAction)
  gitOverlay.addEventListener("pointerdown", function (event) {
    if (event.target === gitOverlay) closeGitPanel()
  })
  gitOverlay.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      event.preventDefault()
      closeGitPanel()
    }
  })
  document.addEventListener("pointerdown", function (event) {
    if (!ledTip.classList.contains("is-open")) return
    if (ledWrap.contains(event.target)) return
    closeTip()
  }, true)

  function setApp(next, updateHash) {
    if (!apps.length) return
    closeTip()
    closeMenu(false)
    index = (next + apps.length) % apps.length
    const app = apps[index]

    titleText.textContent = app.title || "Untitled"
    titleButton.title = "Show all apps"
    menuCurrentTitle.textContent = app.title || "Untitled"
    countEl.textContent = pad(index + 1) + " / " + pad(apps.length)
    document.title = (app.title ? app.title + " — " : "") + "Apps"
    frame.title = app.title || "App"
    if (app.kind === "project" && window.__RIBBON_CARD_HTML__) {
      frame.removeAttribute("src")
      frame.srcdoc = cardPage(app)
    } else if (app.kind === "markdown" && app.markdownHtml) {
      frame.removeAttribute("src")
      frame.srcdoc = markdownPage(app)
    } else {
      frame.removeAttribute("srcdoc")
      frame.src = app.url
    }
    setGit(app.git)
    refreshGit(app)
    updateCurrentStar()

    if (apps.length < 2) disablePaging()

    if (updateHash !== false) {
      const nextHash = "#" + encodeURIComponent(appHash(app))
      try {
        history.replaceState(null, "", nextHash)
      } catch (error) {
        location.hash = encodeURIComponent(appHash(app))
      }
    }

    lastTargets.clear()
    suppressScrollUntil = Date.now() + 300
  }

  function setGit(git) {
    const lights = gitLights(git)

    ledRepo.className = "led " + lights.repoClass
    ledChanges.className = "led " + lights.changesClass
    ledRemote.className = "led " + lights.remoteClass
    tipRepoDot.className = "led " + lights.repoClass
    tipChangesDot.className = "led " + lights.changesClass
    tipRemoteDot.className = "led " + lights.remoteClass

    const repoText = repoTip(git)
    const changesText = changesTip(git, lights.dirty, lights.count)
    const remoteText = remoteTip(git, lights.hasRemote)
    tipRepoText.textContent = repoText
    tipChangesText.textContent = changesText
    tipRemoteText.textContent = remoteText
    ledsWrap.setAttribute("aria-label", repoText + ". " + changesText + ". " + remoteText)

    setLedLabel("repo", repoText, lights.repo ? "Click for Git actions" : "Click to create a repository")
    setLedLabel("changes", changesText, lights.dirty ? "Click to commit" : "Nothing to commit")
    setLedLabel(
      "remote",
      remoteText,
      !lights.hasRemote
        ? "Click to create a remote"
        : git && git.ahead
          ? "Click to push"
          : git && git.state === "clean" && /github\.com[:/]/i.test(git.remote_url || "")
            ? "Click to publish with Pages"
            : "Remote status"
    )
  }

  function setLedLabel(name, text, hint) {
    for (let i = 0; i < ledButtons.length; i += 1) {
      if (ledButtons[i].getAttribute("data-led") === name) {
        ledButtons[i].setAttribute("aria-label", text + ". " + hint)
        ledButtons[i].title = text + " — " + hint
        return
      }
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

  function openTip(pin) {
    if (pin) tipPinned = true
    ledTip.classList.add("is-open")
    ledTip.setAttribute("aria-hidden", "false")
    if (tipTimer) {
      clearTimeout(tipTimer)
      tipTimer = 0
    }
    if (!hoverCapable && tipPinned) {
      tipTimer = setTimeout(closeTip, 5000)
    }
  }

  function closeTip() {
    tipPinned = false
    ledTip.classList.remove("is-open")
    ledTip.setAttribute("aria-hidden", "true")
    if (tipTimer) {
      clearTimeout(tipTimer)
      tipTimer = 0
    }
  }

  function closeTipIfUnpinned() {
    if (!tipPinned) closeTip()
  }

  function refreshGit(app) {
    if (!app || !app.dir) return
    if (location.protocol !== "http:" && location.protocol !== "https:") return
    fetch("/__ribbon/git.json?dir=" + encodeURIComponent(app.dir), {
      cache: "no-store"
    })
      .then(function (response) {
        return response.ok ? response.json() : null
      })
      .then(function (data) {
        if (!data || app !== apps[index]) return
        app.git = data
        setGit(data)
      })
      .catch(function () {})
  }

  function step(direction) {
    if (apps.length < 2) return
    setApp(index + direction)
  }

  function random() {
    if (apps.length < 2) return
    let pick = Math.floor(Math.random() * (apps.length - 1))
    if (pick >= index) pick += 1
    setApp(pick)
  }

  function escapeAttribute(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[ch]
    })
  }

  function cardPage(app) {
    return '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
      '<meta name="viewport" content="width=device-width, initial-scale=1">' +
      '<link rel="stylesheet" href="card.css"></head><body>' +
      window.__RIBBON_CARD_HTML__(app) + "</body></html>"
  }

  function markdownPage(app) {
    const cardStylesheet = new URL("card.css", location.href).href
    const markdownStylesheet = new URL("markdown.css", location.href).href
    let base
    try {
      base = new URL(app.url || "", location.href).href.replace(/[^/]*$/, "")
    } catch (error) {
      base = ""
    }
    return '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
      '<meta name="viewport" content="width=device-width, initial-scale=1">' +
      (base ? '<base href="' + escapeAttribute(base) + '">' : "") +
      '<link rel="stylesheet" href="' + escapeAttribute(cardStylesheet) + '">' +
      '<link rel="stylesheet" href="' + escapeAttribute(markdownStylesheet) + '">' +
      '</head><body class="rc-doc-body">' +
      (app.markdownHtml || "") + "</body></html>"
  }

  function appHash(app) {
    if (!app) return ""
    return app.kind === "project" ? "project:" + (app.dir || app.path || "") : app.url
  }

  function reloadApp() {
    closeMenu(false)
    if (!apps.length) return
    if (apps[index].kind === "project" || apps[index].kind === "markdown") {
      setApp(index, false)
      return
    }
    try {
      frame.contentWindow.location.reload()
    } catch (error) {
      frame.src = apps[index].url
    }
  }

  function appKey(app) {
    return app ? app.dir || app.url || "" : ""
  }

  function readFavorites() {
    try {
      const stored = JSON.parse(localStorage.getItem("ribbon:favorites") || "[]")
      if (Array.isArray(stored)) {
        return new Set(stored.filter(function (item) {
          return typeof item === "string"
        }))
      }
    } catch (error) { /* ignore unreadable favorites */ }
    return new Set()
  }

  function saveFavorites() {
    try {
      localStorage.setItem("ribbon:favorites", JSON.stringify(Array.from(favorites)))
    } catch (error) { /* storage may be unavailable */ }
  }

  function isFavorite(app) {
    return !!app && favorites.has(appKey(app))
  }

  function currentApp() {
    return index >= 0 ? apps[index] : null
  }

  function updateCurrentStar() {
    const app = currentApp()
    const favorite = isFavorite(app)
    const name = app ? app.title || "this app" : "this app"
    const label = (favorite ? "Remove " : "Add ") +
      name + (favorite ? " from favorites" : " to favorites")
    for (let i = 0; i < starButtons.length; i += 1) {
      const button = starButtons[i]
      button.disabled = !app
      button.setAttribute("aria-pressed", favorite ? "true" : "false")
      button.textContent = favorite ? "★" : "☆"
      button.title = label
      button.setAttribute("aria-label", label)
    }
  }

  const LED_WORK = { ok: 0, warn: 1, bad: 2, off: 3 }

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

  // Fewest green lights first, then the worst remaining light. This puts
  // apps that need the most Git work at the top of the app menu.
  function gitWorkRank(app) {
    const lights = gitLights(app && app.git)
    const classes = [ lights.repoClass, lights.changesClass, lights.remoteClass ]
    let green = 0
    let severity = 0
    for (let i = 0; i < classes.length; i += 1) {
      if (classes[i] === "ok") green += 1
      else severity += LED_WORK[classes[i]]
    }
    return { green: green, severity: severity }
  }

  function menuLights(git) {
    const lights = gitLights(git)
    const classes = [ lights.repoClass, lights.changesClass, lights.remoteClass ]
    const wrap = document.createElement("span")
    wrap.className = "menu-leds"
    wrap.setAttribute("role", "img")
    for (let i = 0; i < classes.length; i += 1) {
      const dot = document.createElement("span")
      dot.className = "led " + classes[i]
      dot.setAttribute("aria-hidden", "true")
      wrap.appendChild(dot)
    }
    const label = [
      repoTip(git),
      changesTip(git, lights.dirty, lights.count),
      remoteTip(git, lights.hasRemote)
    ].join(". ")
    wrap.setAttribute("aria-label", label)
    wrap.title = label
    return wrap
  }

  function favoriteRow(app, appIndex) {
    const favorite = isFavorite(app)
    const row = document.createElement("div")
    row.className = "menu-row" + (appIndex === index ? " is-current" : "")

    const open = document.createElement("button")
    open.type = "button"
    open.className = "menu-app"
    open.setAttribute("data-app", String(appIndex))
    if (appIndex === index) open.setAttribute("aria-current", "true")

    const title = document.createElement("span")
    title.className = "menu-app-title"
    if (app.icon) {
      const glyph = document.createElement("span")
      glyph.className = "menu-app-glyph"
      glyph.textContent = app.icon
      glyph.title = app.type || "Project"
      glyph.setAttribute("aria-hidden", "true")
      if (app.color) glyph.style.color = app.color
      title.appendChild(glyph)
    }
    title.appendChild(document.createTextNode(app.title || "Untitled"))

    const dir = document.createElement("span")
    dir.className = "menu-app-dir"
    dir.textContent = "/" + (app.dir || "")

    open.appendChild(title)
    open.appendChild(dir)

    const star = document.createElement("button")
    star.type = "button"
    star.className = "row-star"
    star.setAttribute("data-star", appKey(app))
    star.setAttribute("aria-pressed", favorite ? "true" : "false")
    star.title = favorite ? "Remove from favorites" : "Add to favorites"
    star.setAttribute(
      "aria-label",
      (favorite ? "Remove " : "Add ") +
        (app.title || "app") +
        (favorite ? " from favorites" : " to favorites")
    )
    star.textContent = favorite ? "★" : "☆"

    row.appendChild(menuLights(app.git))
    row.appendChild(open)
    row.appendChild(star)
    return row
  }

  function matchesQuery(app, query) {
    if (!query) return true
    const haystack = String(app.title || "").toLowerCase() +
      " " + String(app.dir || "").toLowerCase() +
      " " + String(app.type || "").toLowerCase()
    return haystack.indexOf(query) !== -1
  }

  function renderMenu(query) {
    const needle = (query || "").trim().toLowerCase()
    menuFavList.textContent = ""
    menuAllList.textContent = ""
    let favoriteCount = 0
    let otherCount = 0
    const rows = []

    apps.forEach(function (app, appIndex) {
      if (!matchesQuery(app, needle)) return
      rows.push({ app: app, appIndex: appIndex })
    })

    rows.sort(function (a, b) {
      const rankA = gitWorkRank(a.app)
      const rankB = gitWorkRank(b.app)
      if (rankA.green !== rankB.green) return rankA.green - rankB.green
      if (rankA.severity !== rankB.severity) return rankB.severity - rankA.severity
      return a.appIndex - b.appIndex
    })

    rows.forEach(function (entry) {
      const app = entry.app
      const appIndex = entry.appIndex
      if (isFavorite(app)) {
        menuFavList.appendChild(favoriteRow(app, appIndex))
        favoriteCount += 1
      } else {
        menuAllList.appendChild(favoriteRow(app, appIndex))
        otherCount += 1
      }
    })

    menuFavSection.hidden = favoriteCount === 0
    menuAllSection.hidden = otherCount === 0
    menuEmpty.hidden = favoriteCount + otherCount > 0
    menuAllHeading.textContent = favoriteCount ? "Other apps" : "All apps"
  }

  function openMenu() {
    if (!apps.length) return
    if (menuOpen) {
      searchInput.focus()
      searchInput.select()
      return
    }
    menuOpen = true
    menuEl.hidden = false
    titleButton.setAttribute("aria-expanded", "true")
    searchInput.value = ""
    renderMenu("")
    updateCurrentStar()
    requestAnimationFrame(function () {
      searchInput.focus()
      searchInput.select()
    })
  }

  function closeMenu(returnFocus) {
    if (!menuOpen) return
    menuOpen = false
    menuEl.hidden = true
    titleButton.setAttribute("aria-expanded", "false")
    if (returnFocus) titleButton.focus()
  }

  function toggleMenu() {
    if (menuOpen) closeMenu(true)
    else openMenu()
  }

  function toggleFavorite(app, focusStar) {
    const key = appKey(app)
    if (!key) return
    if (favorites.has(key)) favorites.delete(key)
    else favorites.add(key)
    saveFavorites()
    renderMenu(searchInput.value)
    updateCurrentStar()
    if (focusStar) {
      const stars = menuEl.querySelectorAll("[data-star]")
      for (let i = 0; i < stars.length; i += 1) {
        if (stars[i].getAttribute("data-star") === key) {
          stars[i].focus()
          break
        }
      }
    }
  }

  function defaultRepoName() {
    const app = currentApp()
    const path = app ? app.dir || app.url || "" : ""
    let name = path.split("/").filter(Boolean).pop() || (app && app.title) || "app"
    name = name.replace(/^\d{4}-\d{2}-\d{2}-/, "")
    name = name.replace(/\.html?$/i, "")
    name = name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "")
    return (name || "app").slice(0, 100)
  }

  function decideGitAction(detail, focus) {
    if (!detail || !detail.repo) return "init"
    if (detail.state === "detached" || detail.state === "conflicted") return "info"
    const dirty = !!(detail.files && detail.files.length)
    const hasRemote = !!detail.has_remote
    const needsPush = hasRemote && detail.state !== "diverged" && (detail.ahead > 0 || !detail.upstream)
    if (focus === "changes" && dirty) return "commit"
    if (focus === "remote") {
      if (!hasRemote) return detail.state === "no-commits" && !dirty ? "info" : "remote"
      if (needsPush) return "push"
      if (!dirty && /github\.com[:/]/i.test(detail.remote_url || "")) return "pages"
    }
    if (dirty) return "commit"
    if (!hasRemote) return detail.state === "no-commits" ? "info" : "remote"
    if (needsPush) return "push"
    return "info"
  }

  function summaryRow(label, value) {
    const row = document.createElement("div")
    row.className = "git-summary-row"
    const labelEl = document.createElement("span")
    labelEl.className = "git-summary-label"
    labelEl.textContent = label
    const valueEl = document.createElement("span")
    valueEl.className = "git-summary-value"
    valueEl.textContent = value
    valueEl.title = value
    row.appendChild(labelEl)
    row.appendChild(valueEl)
    gitSummary.appendChild(row)
  }

  function renderGitUnavailable(message) {
    gitDetail = null
    gitAction = null
    gitBlocked = false
    gitTitle.textContent = "Git unavailable"
    gitSummary.textContent = ""
    summaryRow("Status", message)
    gitFiles.hidden = true
    gitWarnings.hidden = true
    gitMessageField.hidden = true
    gitNameField.hidden = true
    gitVisibilityField.hidden = true
    gitDescriptionField.hidden = true
    gitReadmeField.hidden = true
    gitPagesField.hidden = true
    gitIgnoreField.hidden = true
    gitNote.hidden = true
    gitOutput.hidden = true
    gitStatus.className = "git-status"
    gitStatus.textContent = ""
    gitPrimary.hidden = true
    gitCancel.textContent = "Close"
    gitCancel.focus()
  }

  function renderGitPanel(detail, focus, success, extra) {
    gitDetail = detail
    gitAction = decideGitAction(detail, focus)
    gitBlocked = false
    if (gitAction === "pages" && detail.pages && !detail.pages.index) {
      gitAction = "pages-entry"
    }

    const app = currentApp()
    const titles = {
      init: "Create a Git repository",
      commit: "Commit changes",
      push: "Push commits",
      remote: "Create a GitHub remote",
      pages: "Publish to GitHub Pages",
      "pages-entry": "GitHub Pages needs an index.html",
      info: "Git status"
    }
    const labels = {
      init: "Create repo + commit",
      commit: "Commit changes",
      push: "Push commits",
      remote: "Create repo + push",
      pages: "Publish to GitHub Pages",
      "pages-entry": "Create index.html"
    }
    gitTitle.textContent = titles[gitAction] || "Git status"

    gitSummary.textContent = ""
    summaryRow("Folder", detail.root || (app && (app.dir || app.url)) || "—")
    summaryRow("Branch", detail.branch || "—")
    const fileCount = detail.files ? detail.files.length : 0
    summaryRow(
      "Changes",
      fileCount
        ? fileCount + " file" + (fileCount === 1 ? "" : "s")
        : detail.repo
          ? "clean"
          : "no repository"
    )
    summaryRow("Remote", detail.remote_url || (detail.has_remote ? "configured" : "none"))
    if (detail.repo && detail.has_remote) {
      const sync = []
      if (detail.upstream) {
        if (detail.ahead) sync.push(detail.ahead + " to push")
        if (detail.behind) sync.push(detail.behind + " behind")
        if (!sync.length) sync.push("up to date")
      } else {
        sync.push("no upstream")
      }
      summaryRow("Sync", sync.join(", "))
    }

    const files = detail.files || []
    gitFiles.textContent = ""
    gitFiles.hidden = !((gitAction === "commit" || gitAction === "init") && files.length)
    if (!gitFiles.hidden) {
      files.slice(0, 12).forEach(function (item) {
        const row = document.createElement("div")
        row.className = "git-file"
        const code = document.createElement("span")
        code.className = "git-file-code"
        code.textContent = item.code.trim() || "?"
        const path = document.createElement("span")
        path.className = "git-file-path"
        path.textContent = item.path
        path.title = item.path
        row.appendChild(code)
        row.appendChild(path)
        gitFiles.appendChild(row)
      })
      if (files.length > 12) {
        const more = document.createElement("div")
        more.className = "git-file-more"
        more.textContent = "+" + (files.length - 12) + " more"
        gitFiles.appendChild(more)
      }
    }

    const warnings = (detail.warnings || []).filter(function (warning) {
      return !(
        gitAction === "init" &&
        !detail.has_gitignore &&
        warning.indexOf("No .gitignore") === 0
      )
    })
    gitWarnings.textContent = ""
    gitWarnings.hidden = warnings.length === 0
    warnings.forEach(function (warning) {
      const row = document.createElement("div")
      row.className = "git-warning"
      row.textContent = warning
      gitWarnings.appendChild(row)
    })

    const canWrite = !!gitToken
    gitMessageField.hidden = !(gitAction === "commit" || gitAction === "init")
    if (!gitMessageField.hidden) {
      gitMessage.value = gitAction === "init"
        ? "Initial commit"
        : "Update " + ((app && app.title) || detail.branch || "app")
    }
    gitNameField.hidden = gitAction !== "remote"
    if (!gitNameField.hidden) gitName.value = defaultRepoName()
    gitVisibilityField.hidden = gitAction !== "remote"
    if (!gitVisibilityField.hidden) {
      for (let i = 0; i < gitVisibilityInputs.length; i += 1) {
        gitVisibilityInputs[i].checked = gitVisibilityInputs[i].value === "private"
      }
    }
    gitDescriptionField.hidden = gitAction !== "remote"
    if (!gitDescriptionField.hidden) gitDescription.value = ""
    const readmeMissing = !(detail.readme && detail.readme.exists)
    gitReadmeField.hidden = !(
      (gitAction === "remote" || gitAction === "pages") && readmeMissing
    )
    if (!gitReadmeField.hidden) {
      gitReadme.value = "# " + ((app && app.title) || "App") + "\n\n"
    }
    gitPagesField.hidden = gitAction !== "remote"
    if (!gitPagesField.hidden) gitPages.checked = false
    gitIgnoreField.hidden = gitAction !== "init" || !!detail.has_gitignore
    if (!gitIgnoreField.hidden) gitIgnore.checked = true

    const notes = extra ? [ extra ] : []
    if (!canWrite) notes.push("Git actions are disabled. Start ribbon.py on 127.0.0.1.")
    if ((gitAction === "commit" || gitAction === "init") && detail.repo && detail.identity_ok === false) {
      notes.push(
        'Set your Git name and email first:\n  git config --global user.name "Your Name"\n  git config --global user.email "you@example.com"'
      )
    }
    if (gitAction === "remote" && detail.gh === false) {
      notes.push("GitHub CLI (gh) is not installed. Install it, or add a remote by hand.")
    }
    if (gitAction === "pages" && detail.gh === false) {
      notes.push("GitHub CLI (gh) is not installed. Install it to publish with Pages.")
    }
    if (gitAction === "pages-entry") {
      const entry = detail.pages && detail.pages.entry
      notes.push(
        "GitHub Pages only serves an index.html at the repository root." +
        (entry
          ? " Ribbon will create one that opens " + entry + "."
          : " Add an HTML page first.")
      )
    }
    if (gitAction === "pages") {
      notes.push("This enables GitHub Pages for the current branch and sets the Pages address as the repo homepage.")
    }
    if (detail.state === "detached") notes.push("You are on a detached HEAD. Switch to a branch first.")
    if (detail.state === "conflicted") notes.push("Resolve the merge conflicts, then try again.")
    if (detail.state === "diverged") notes.push("Local and remote have diverged. Pull or rebase before pushing.")
    if (detail.state === "behind" && gitAction === "info") {
      notes.push("The remote has commits you do not have yet.")
    }
    if (gitAction === "info" && !notes.length) notes.push("Everything is in order.")
    gitNote.textContent = notes.join("\n\n")
    gitNote.hidden = notes.length === 0

    gitOutput.hidden = true
    gitOutput.textContent = ""
    gitStatus.className = "git-status" + (success ? " is-good" : "")
    gitStatus.textContent = success || ""

    gitBlocked =
      !canWrite ||
      detail.identity_ok === false && (gitAction === "commit" || gitAction === "init") ||
      (gitAction === "remote" || gitAction === "pages") && detail.gh === false ||
      gitAction === "pages-entry" && !(detail.pages && detail.pages.entry)
    gitPrimary.textContent = labels[gitAction] || ""
    gitPrimary.hidden = !labels[gitAction]
    gitPrimary.disabled = gitBlocked
    gitCancel.textContent = gitAction === "info" ? "Close" : "Cancel"
    gitCancel.disabled = false
    gitClose.disabled = false

    if (!gitReadmeField.hidden) gitReadme.focus()
    else if (gitAction === "commit" || gitAction === "init") gitMessage.focus()
    else if (gitAction === "remote") gitName.focus()
    else if (gitAction === "push" || gitAction === "pages" || gitAction === "pages-entry") gitPrimary.focus()
    else gitCancel.focus()
  }

  function openGitPanel(focus) {
    const app = currentApp()
    if (!app || !gitOverlay.hidden) return
    closeMenu(false)
    closeTip()
    gitReturnFocus = document.activeElement
    gitOverlay.hidden = false
    gitBusy = false
    gitStatus.className = "git-status"
    gitStatus.textContent = ""
    gitOutput.hidden = true
    gitOutput.textContent = ""
    gitTitle.textContent = "Checking Git…"
    gitSummary.textContent = ""
    gitFiles.hidden = true
    gitWarnings.hidden = true
    gitNote.hidden = true
    gitMessageField.hidden = true
    gitNameField.hidden = true
    gitVisibilityField.hidden = true
    gitDescriptionField.hidden = true
    gitReadmeField.hidden = true
    gitPagesField.hidden = true
    gitIgnoreField.hidden = true
    gitPrimary.hidden = true

    if (location.protocol !== "http:" && location.protocol !== "https:") {
      renderGitUnavailable("Start the ribbon server to use Git actions.")
      return
    }

    gitSession
      .then(function (session) {
        gitToken = session.token
        if (gitOverlay.hidden) return null
        const dir = app.dir || app.url || ""
        return fetch("/__ribbon/git.json?dir=" + encodeURIComponent(dir), { cache: "no-store" })
          .then(function (response) {
            if (!response.ok) throw new Error("HTTP " + response.status)
            return response.json()
          })
          .then(function (detail) {
            if (gitOverlay.hidden) return
            setGit(detail)
            if (app === apps[index]) app.git = detail
            renderGitPanel(detail, focus, "")
          })
      })
      .catch(function (error) {
        renderGitUnavailable("Could not read Git status: " + (error.message || error))
      })
  }

  function closeGitPanel() {
    if (gitBusy) return
    gitOverlay.hidden = true
    gitDetail = null
    gitAction = null
    if (gitReturnFocus && gitReturnFocus.focus) {
      try {
        gitReturnFocus.focus()
      } catch (error) { /* target may be gone */ }
    }
    gitReturnFocus = null
  }

  function setGitBusy(busy) {
    gitBusy = busy
    gitPrimary.disabled = busy || gitBlocked
    gitCancel.disabled = busy
    gitClose.disabled = busy
    if (busy) {
      gitPrimary.textContent = "Working…"
    } else if (gitAction) {
      const labels = {
        init: "Create repo + commit",
        commit: "Commit changes",
        push: "Push commits",
        remote: "Create repo + push",
        pages: "Publish to GitHub Pages",
        "pages-entry": "Create index.html"
      }
      gitPrimary.textContent = labels[gitAction] || "Continue"
    }
  }

  function showGitError(data) {
    const error = (data && (data.error || data.message)) || "The Git action failed."
    const output = (data && data.output) || ""
    gitStatus.className = "git-status is-bad"
    gitStatus.textContent = error.split("\n")[0].slice(0, 140)
    gitOutput.textContent = [ error, output ].filter(Boolean).join("\n\n")
    gitOutput.hidden = !gitOutput.textContent
  }

  function submitGitAction() {
    if (gitBusy || !gitAction) return
    const app = currentApp()
    if (!app) return

    const payload = { action: gitAction, dir: app.dir || app.url || "" }
    if (gitAction === "init" || gitAction === "commit") {
      payload.message = gitMessage.value.trim()
      if (!payload.message) {
        gitMessage.focus()
        return
      }
    }
    if (gitAction === "init") payload.gitignore = gitIgnore.checked
    if (gitAction === "remote") {
      payload.name = gitName.value.trim()
      if (!payload.name) {
        gitName.focus()
        return
      }
      const checked = document.querySelector('input[name="git-visibility"]:checked')
      payload.visibility = checked ? checked.value : "private"
      payload.description = gitDescription.value.trim()
      payload.pages = gitPages.checked
    }
    if (!gitReadmeField.hidden) payload.readme = gitReadme.value

    setGitBusy(true)
    gitStatus.className = "git-status"
    gitStatus.textContent = "Working…"
    gitOutput.hidden = true
    gitOutput.textContent = ""

    fetch("/__ribbon/git", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Ribbon-Token": gitToken
      },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        return response.json()
          .catch(function () {
            return { ok: false, error: "Unexpected response from the server." }
          })
          .then(function (data) {
            data.statusCode = response.status
            return data
          })
      })
      .then(function (data) {
        if (!data || !data.ok) {
          setGitBusy(false)
          showGitError(data)
          return
        }
        if (data.status) {
          setGit(data.status)
          if (app === apps[index]) app.git = data.status
        }
        let message = {
          init: "Repository created and first commit made.",
          commit: "Changes committed.",
          push: "Commits pushed.",
          remote: "GitHub repo created and pushed.",
          pages: "GitHub Pages is on.",
          "pages-entry": "Created index.html. Commit and push it, then publish again."
        }[payload.action] || "Done."
        let extra = ""
        if (payload.action === "remote" || payload.action === "pages") {
          if (data.pages_url) {
            extra = "GitHub Pages: " + data.pages_url
            if (data.pages_error) extra += "\n" + data.pages_error
          } else if (payload.pages && data.pages_error) {
            message = "GitHub repo created, but Pages setup failed."
            extra = data.pages_error
          }
        }
        if (data.readme_written) {
          extra = [ "README.md was committed and pushed.", extra ].filter(Boolean).join("\n")
        }
        setGitBusy(false)
        renderGitPanel(data.status || gitDetail, null, message, extra)
      })
      .catch(function (error) {
        setGitBusy(false)
        showGitError({ error: error.message || "The request failed." })
      })
  }

  function disablePaging() {
    for (let i = 0; i < buttons.length; i += 1) {
      const action = buttons[i].getAttribute("data-act")
      if (action !== "hide") buttons[i].disabled = true
    }
  }

  function pad(number) {
    const width = String(apps.length).length
    let value = String(number)
    while (value.length < width) value = "0" + value
    return value
  }

  function wireFrame() {
    let win
    let doc
    try {
      win = frame.contentWindow
      doc = frame.contentDocument
    } catch (error) {
      return
    }
    if (!win || !doc || wiredDocs.has(doc)) return
    wiredDocs.add(doc)

    try {
      win.addEventListener("scroll", onScroll, { passive: true })
      doc.addEventListener("scroll", onScroll, { passive: true, capture: true })
      doc.addEventListener("pointerdown", closeTip, true)
      doc.addEventListener("pointerdown", function () {
        closeMenu(false)
      }, true)
      win.addEventListener("focus", function () {
        closeMenu(false)
      })
      win.addEventListener("keydown", onKey, true)
    } catch (error) {
      return
    }
  }

  let pendingScroll = null

  function onScroll(event) {
    if (pendingScroll) return
    pendingScroll = event
    requestAnimationFrame(processScroll)
  }

  function processScroll() {
    const event = pendingScroll
    pendingScroll = null
    if (manualHidden || Date.now() < suppressScrollUntil) return
    if (event && event.target && menuEl.contains(event.target)) return

    let win
    let doc
    try {
      win = frame.contentWindow
      doc = frame.contentDocument
    } catch (error) {
      return
    }
    if (!win || !doc) return

    let target = event && event.target
    if (
      target === win ||
      target === doc ||
      target === doc.documentElement ||
      target === doc.body
    ) {
      target = null
    }

    const y = target
      ? target.scrollTop
      : (win.scrollY || win.pageYOffset || doc.documentElement.scrollTop || 0)
    const hasPrevious = lastTargets.has(target)
    const previous = hasPrevious ? lastTargets.get(target) : y
    const delta = y - previous

    if (Math.abs(delta) < 10) {
      if (!hasPrevious) lastTargets.set(target, y)
      return
    }

    let nextHidden
    if (y <= 8) nextHidden = false
    else if (delta > 0 && y > 48) nextHidden = true
    else if (delta < 0) nextHidden = false
    else return

    lastTargets.set(target, y)
    if (nextHidden !== autoHidden) {
      autoHidden = nextHidden
      applyHidden()
    }
  }

  function onKey(event) {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
    const target = event.target
    if (
      target &&
      (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
    ) {
      return
    }

    const key = event.key
    if (!gitOverlay.hidden) {
      if (key === "Escape") {
        closeGitPanel()
        event.preventDefault()
        event.stopPropagation()
      }
      return
    }
    if (key === "Escape" && menuOpen) {
      closeMenu(true)
      event.preventDefault()
      event.stopPropagation()
      return
    }
    if (key === "/") {
      openMenu()
      event.preventDefault()
      event.stopPropagation()
      return
    }
    if (menuOpen) return
    if (key === "Escape" && ledTip.classList.contains("is-open")) {
      closeTip()
      event.preventDefault()
      event.stopPropagation()
      return
    }

    let handled = true
    if (key === "[") step(-1)
    else if (key === "]") step(1)
    else if (key === "r" || key === "R") {
      if (event.shiftKey) reloadApp()
      else random()
    } else if (key === "h" || key === "H") toggleHidden()
    else handled = false

    if (handled) {
      event.preventDefault()
      event.stopPropagation()
    }
  }

  function toggleHidden() {
    if (!manualHidden && autoHidden) {
      autoHidden = false
      applyHidden()
      return
    }
    setManual(!manualHidden)
  }

  function setManual(hidden) {
    manualHidden = hidden
    if (hidden) autoHidden = false
    else lastTargets.clear()
    try {
      sessionStorage.setItem(STORAGE_KEY, hidden ? "1" : "0")
    } catch (error) { /* storage may be unavailable */ }
    applyHidden()
  }

  function applyHidden() {
    const gone = manualHidden || autoHidden
    if (gone) {
      closeTip()
      closeMenu(false)
    }
    document.documentElement.classList.toggle("is-hidden", gone)
    if (gone) bar.setAttribute("inert", "")
    else bar.removeAttribute("inert")
    peek.classList.toggle("is-shown", manualHidden)
    peek.tabIndex = manualHidden ? 0 : -1
  }

  function readHidden() {
    try {
      return sessionStorage.getItem(STORAGE_KEY) === "1"
    } catch (error) {
      return false
    }
  }

  function readHash() {
    const hash = location.hash.replace(/^#/, "")
    if (!hash) return ""
    try {
      return decodeURIComponent(hash)
    } catch (error) {
      return hash
    }
  }

  applyHidden()
})()

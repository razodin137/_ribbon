/* FROZEN — do not add bar features here.
 *
 * shell.js is the no-server host. The shared bar lives in bar.js; this file
 * keeps only the iframe, hash, hide/scroll, and reload concerns. New bar
 * features land in bar.js, never here.
 */
(function () {
  "use strict"

  const bar = window.__RIBBON_BAR__

  const apps = (Array.isArray(window.__RIBBON_APPS__) ? window.__RIBBON_APPS__ : []).filter(function (app) {
    return app && typeof app.url === "string" && app.url
  })

  const barEl = document.getElementById("bar")
  const countEl = document.getElementById("count")
  const titleButton = document.getElementById("title")
  const titleText = document.getElementById("title-text")
  const frame = document.getElementById("app")
  const empty = document.getElementById("empty")
  const peek = document.getElementById("peek")
  const ledsWrap = document.getElementById("leds")
  const ledButtons = document.querySelectorAll(".led-btn")
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
  const canReachServer = location.protocol === "http:" || location.protocol === "https:"
  const gitSession = canReachServer
    ? fetch("/__ribbon/manifest.json", { cache: "no-store" })
      .then(function (response) {
        return response.ok ? response.json() : null
      })
      .then(function (data) {
        return { token: (data && data.token) || "", write: !!(data && data.write) }
      })
      .catch(function () {
        return { token: "", write: false }
      })
    : Promise.resolve({ token: "", write: false })

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

  const ui = bar.createBar({
    root: document,
    refs: {
      menuEl: menuEl,
      menuCurrentTitle: menuCurrentTitle,
      menuCurrentMeta: null,
      menuChannels: null,
      keepButton: null,
      parkButton: null,
      starButtons: starButtons,
      searchInput: searchInput,
      menuFavSection: menuFavSection,
      menuAllSection: menuAllSection,
      menuFavList: menuFavList,
      menuAllList: menuAllList,
      menuAllHeading: menuAllHeading,
      menuEmpty: menuEmpty,
      titleButton: titleButton,
      ledButtons: ledButtons,
      ledsWrap: ledsWrap,
      ledTip: ledTip,
      ledRepo: ledRepo,
      ledChanges: ledChanges,
      ledRemote: ledRemote,
      tipRepoDot: tipRepoDot,
      tipChangesDot: tipChangesDot,
      tipRemoteDot: tipRemoteDot,
      tipRepoText: tipRepoText,
      tipChangesText: tipChangesText,
      tipRemoteText: tipRemoteText,
      gitOverlay: gitOverlay,
      gitTitle: gitTitle,
      gitSummary: gitSummary,
      gitFiles: gitFiles,
      gitWarnings: gitWarnings,
      gitMessageField: gitMessageField,
      gitMessage: gitMessage,
      gitNameField: gitNameField,
      gitName: gitName,
      gitVisibilityField: gitVisibilityField,
      gitVisibilityInputs: gitVisibilityInputs,
      gitDescriptionField: gitDescriptionField,
      gitDescription: gitDescription,
      gitReadmeField: gitReadmeField,
      gitReadme: gitReadme,
      gitPagesField: gitPagesField,
      gitPages: gitPages,
      gitIgnoreField: gitIgnoreField,
      gitIgnore: gitIgnore,
      gitNote: gitNote,
      gitOutput: gitOutput,
      gitStatus: gitStatus,
      gitCancel: gitCancel,
      gitPrimary: gitPrimary,
      gitClose: gitClose
    },
    apps: apps,
    index: index,
    signals: {},
    canDelete: false,
    channel: {
      id: "all",
      matches: function () { return true },
      label: function () { return "All apps" }
    },
    getToken: function () {
      return gitSession.then(function (session) { return session.token })
    },
    onSelect: function (app, appIndex) { setApp(appIndex) }
  })

  frame.addEventListener("load", wireFrame)

  if (!apps.length) {
    empty.hidden = false
    frame.hidden = true
    titleText.textContent = "No apps listed"
    titleButton.title = "Show all apps"
    menuCurrentTitle.textContent = "No apps listed"
    countEl.textContent = "00 / 00"
    disablePaging()
    ui.setApps([])
    ui.setIndex(-1)
    ui.setGit(null)
    ui.updateCurrentStar()
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

  barEl.addEventListener("click", function (event) {
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

  document.addEventListener("pointerdown", function (event) {
    if (barEl.contains(event.target)) return
    ui.closeMenu(false)
  }, true)

  function setApp(next, updateHash) {
    if (!apps.length) return
    ui.closeTip()
    ui.closeMenu(false)
    index = (next + apps.length) % apps.length
    ui.setIndex(index)
    const app = apps[index]

    titleText.textContent = app.title || "Untitled"
    titleButton.title = "Show all apps"
    menuCurrentTitle.textContent = app.title || "Untitled"
    countEl.textContent = bar.pad(index + 1, apps.length) + " / " + bar.pad(apps.length, apps.length)
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
    ui.setGit(app.git)
    refreshGit(app)
    ui.updateCurrentStar()

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

  function refreshGit(app) {
    if (!app || !app.dir) return
    if (!canReachServer) return
    fetch("/__ribbon/git.json?dir=" + encodeURIComponent(app.dir), {
      cache: "no-store"
    })
      .then(function (response) {
        return response.ok ? response.json() : null
      })
      .then(function (data) {
        if (!data || app !== apps[index]) return
        app.git = data
        ui.setGit(data)
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

  function cardPage(app) {
    const data = JSON.stringify(app).replace(/</g, "\\u003c")
    return '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
      '<meta name="viewport" content="width=device-width, initial-scale=1">' +
      '<link rel="stylesheet" href="card.css">' +
      "<script>window.__RIBBON_CARD_APP__ = " + data + ";</script>" +
      '<script src="card.js" defer></script></head><body>' +
      '<div id="ribbon-card"></div></body></html>'
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
      (base ? '<base href="' + bar.escapeAttribute(base) + '">' : "") +
      '<link rel="stylesheet" href="' + bar.escapeAttribute(cardStylesheet) + '">' +
      '<link rel="stylesheet" href="' + bar.escapeAttribute(markdownStylesheet) + '">' +
      '</head><body class="rc-doc-body">' +
      (app.markdownHtml || "") + "</body></html>"
  }

  function appHash(app) {
    if (!app) return ""
    return app.kind === "project" ? "project:" + (app.dir || app.path || "") : app.url
  }

  function reloadApp() {
    ui.closeMenu(false)
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

  function disablePaging() {
    for (let i = 0; i < buttons.length; i += 1) {
      const action = buttons[i].getAttribute("data-act")
      if (action !== "hide") buttons[i].disabled = true
    }
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
      doc.addEventListener("pointerdown", function () { ui.closeTip() }, true)
      doc.addEventListener("pointerdown", function () {
        ui.closeMenu(false)
      }, true)
      win.addEventListener("focus", function () {
        ui.closeMenu(false)
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
        ui.closeGitPanel()
        event.preventDefault()
        event.stopPropagation()
      }
      return
    }
    if (key === "Escape" && ui.isMenuOpen()) {
      ui.closeMenu(true)
      event.preventDefault()
      event.stopPropagation()
      return
    }
    if (key === "/") {
      ui.openMenu()
      event.preventDefault()
      event.stopPropagation()
      return
    }
    if (ui.isMenuOpen()) return
    if (key === "Escape" && ui.isTipOpen()) {
      ui.closeTip()
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
      ui.closeTip()
      ui.closeMenu(false)
    }
    document.documentElement.classList.toggle("is-hidden", gone)
    if (gone) barEl.setAttribute("inert", "")
    else barEl.removeAttribute("inert")
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

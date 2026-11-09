/* Ribbon — a floating, auto-hiding switcher for a folder of HTML apps.
 *
 * ribbon.py renders the bar shell as declarative shadow DOM at the top of
 * <body>, then injects these scripts. This file adopts that shadow root and
 * wires it up:
 *   <script src="/__ribbon/bar.js" defer></script>
 *   <script src="/__ribbon/ribbon.js" defer></script>
 */
(function () {
  "use strict"

  const bar = window.__RIBBON_BAR__

  if (window.__RIBBON_MOUNTED__) return
  if (window.self !== window.top) return
  window.__RIBBON_MOUNTED__ = true

  const scriptEl = document.currentScript || document.querySelector("script[data-ribbon]")
  let scriptBase = "/__ribbon/"
  const baseAttr = scriptEl && scriptEl.getAttribute("data-ribbon-base")
  if (baseAttr) {
    try {
      scriptBase = new URL("__ribbon/", baseAttr).href
    } catch (_) { /* keep the default base */ }
  } else if (scriptEl && scriptEl.src) {
    try {
      scriptBase = new URL(".", scriptEl.src).href
    } catch (_) { /* keep the default base */ }
  }

  // A served page loads the bar beside its own assets. The extension's new
  // tab loads the same bar from the extension and points it back at the
  // server, so app paths must resolve against the server, not the page.
  function absoluteUrl(url) {
    try {
      return new URL(url, scriptBase).href
    } catch (_) {
      return url
    }
  }
  const CACHE_KEY = "ribbon:apps:" + scriptBase
  const DECK_KEY = "ribbon:deck:" + scriptBase
  const CHANNEL_KEY = "ribbon:channel:" + scriptBase

  const STORAGE_KEY = "ribbon:hidden"
  const SCROLL_KEY = "ribbon:scroll"

  function boot() {
    if (document.body) {
      start()
    } else {
      document.addEventListener("DOMContentLoaded", start, { once: true })
    }
  }

  function start() {
    let manifestUrl
    try {
      manifestUrl = new URL("manifest.json", scriptBase).href
    } catch (_) {
      return
    }

    // Draw the bar from the last list straight away, then refresh it when the
    // manifest arrives. A cached entry may name a project deleted since it was
    // stored, so hold navigation until the first manifest settles.
    const cached = readCachedApps()
    let mounted = null
    let refreshing = null
    // Focus and visibility events arrive in bursts when the user alt-tabs, so
    // ignore them for a moment after the last manifest fetch.
    const REFRESH_MIN_MS = 2000
    let lastRefresh = 0

    function applyManifest(data) {
      const apps = Array.isArray(data) ? data : data && data.apps
      if (!Array.isArray(apps) || !apps.length) return
      const meta = Array.isArray(data)
        ? null
        : {
          state: data.state,
          token: data.token,
          write: data.write
        }
      writeCachedApps(apps)
      if (mounted) mounted.update(apps, meta)
      else mounted = mount(apps, meta, refresh)
    }

    // No watcher reaches every platform and mount, so ask again whenever the
    // page comes back into view or its menu opens.
    function refresh() {
      if (refreshing) return refreshing
      lastRefresh = Date.now()
      refreshing = fetch(manifestUrl, { cache: "no-store" })
        .then(function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status)
          return response.json()
        })
        .then(applyManifest)
        .catch(function () {
          /* No manifest: stay quiet. */
        })
        .then(function () {
          refreshing = null
        })
      return refreshing
    }

    function refreshIfVisible() {
      if (document.hidden) return
      if (Date.now() - lastRefresh < REFRESH_MIN_MS) return
      refresh()
    }

    if (cached) mounted = mount(cached, null, refresh, true)
    refresh().then(function () {
      // No manifest means the cached list is all we have. Release the hold
      // rather than leave the bar unable to navigate.
      if (mounted) mounted.setStale(false)
    })
    document.addEventListener("visibilitychange", refreshIfVisible)
    window.addEventListener("focus", refreshIfVisible)
  }

  function readCachedApps() {
    try {
      const data = JSON.parse(sessionStorage.getItem(CACHE_KEY) || "null")
      const apps = Array.isArray(data) ? data : data && data.apps
      return Array.isArray(apps) && apps.length ? apps : null
    } catch (_) {
      return null
    }
  }

  function writeCachedApps(apps) {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify(apps))
    } catch (_) { /* storage may be unavailable */ }
  }

  function shadowRootFor(host) {
    if (host.shadowRoot) return host.shadowRoot
    const template = host.querySelector("template[shadowrootmode], template[shadowroot]")
    if (!template) return null
    const shadow = host.attachShadow({ mode: "open" })
    shadow.appendChild(template.content.cloneNode(true))
    template.remove()
    return shadow
  }

  function mount(rawApps, meta, refreshManifest, cached) {
    // A mount from the session cache may be one manifest round trip out of
    // date, so navigation waits until the list is confirmed.
    let stale = !!cached
    meta = meta || {}
    let apps = rawApps.filter(function (app) {
      return app && typeof app.url === "string" && app.url
    })
    if (!apps.length) return

    // A page that does not scroll is a little wider than one that does, which
    // moves the right-aligned buttons. Reserve the gutter on every page so the
    // controls stay in the same place from app to app.
    document.documentElement.style.setProperty(
      "scrollbar-gutter",
      "stable",
      "important"
    )

    const host = document.querySelector("[data-ribbon-host]")
    const shadow = host ? shadowRootFor(host) : null
    if (!shadow) return

    const homeUrl = scriptEl && scriptEl.getAttribute("data-ribbon-home")
    if (homeUrl) {
      const homeWrap = shadow.querySelector("[data-home]")
      const homeLink = homeWrap && homeWrap.querySelector("[data-home-link]")
      if (homeLink) homeLink.href = homeUrl
      if (homeWrap) homeWrap.hidden = false
    }

    const barEl = shadow.querySelector(".bar")
    const countEl = shadow.querySelector(".count")
    const titleButton = shadow.querySelector(".title")
    const titleText = shadow.querySelector(".title-text")
    const peekEl = shadow.querySelector(".peek")
    const ledRepo = shadow.querySelector('[data-led-dot="repo"]')
    const ledChanges = shadow.querySelector('[data-led-dot="changes"]')
    const ledRemote = shadow.querySelector('[data-led-dot="remote"]')
    const ledsWrap = shadow.querySelector(".leds")
    const ledButtons = shadow.querySelectorAll(".led-btn")
    const ledTip = shadow.querySelector(".led-tip")
    const tipRepoDot = ledTip.querySelector('[data-tip-led="repo"]')
    const tipChangesDot = ledTip.querySelector('[data-tip-led="changes"]')
    const tipRemoteDot = ledTip.querySelector('[data-tip-led="remote"]')
    const tipRepoText = ledTip.querySelector('[data-tip-text="repo"]')
    const tipChangesText = ledTip.querySelector('[data-tip-text="changes"]')
    const tipRemoteText = ledTip.querySelector('[data-tip-text="remote"]')
    const buttons = shadow.querySelectorAll("button[data-act]")
    const contentsButton = shadow.querySelector('[data-act="contents"]')
    const cardOverlay = shadow.querySelector(".card-overlay")
    const cardFrame = shadow.querySelector(".card-frame")
    const cardClose = shadow.querySelector(".card-close")

    const gitToken = scriptEl ? scriptEl.getAttribute("data-ribbon-token") || "" : ""
    const gitOverlay = shadow.querySelector(".git-overlay")
    const gitTitle = shadow.querySelector(".git-title")
    const gitSummary = shadow.querySelector(".git-summary")
    const gitFiles = shadow.querySelector(".git-files")
    const gitWarnings = shadow.querySelector(".git-warnings")
    const gitMessageField = shadow.querySelector(".git-message-field")
    const gitMessage = shadow.querySelector(".git-message")
    const gitNameField = shadow.querySelector(".git-name-field")
    const gitName = shadow.querySelector(".git-name")
    const gitVisibilityField = shadow.querySelector(".git-visibility-field")
    const gitVisibilityInputs = shadow.querySelectorAll('input[name="git-visibility"]')
    const gitDescriptionField = shadow.querySelector(".git-description-field")
    const gitDescription = shadow.querySelector(".git-description")
    const gitReadmeField = shadow.querySelector(".git-readme-field")
    const gitReadme = shadow.querySelector(".git-readme")
    const gitPagesField = shadow.querySelector(".git-pages-field")
    const gitPages = shadow.querySelector(".git-pages")
    const gitIgnoreField = shadow.querySelector(".git-ignore-field")
    const gitIgnore = shadow.querySelector(".git-ignore")
    const gitNote = shadow.querySelector(".git-note")
    const gitOutput = shadow.querySelector(".git-output")
    const gitStatus = shadow.querySelector(".git-status")
    const gitCancel = shadow.querySelector(".git-cancel")
    const gitPrimary = shadow.querySelector(".git-primary")
    const gitClose = shadow.querySelector(".git-close")

    const deleteOverlay = shadow.querySelector(".delete-overlay")
    const deleteTitle = shadow.querySelector(".delete-title")
    const deletePath = shadow.querySelector(".delete-path")
    const deleteCommand = shadow.querySelector(".delete-command")
    const deleteOutput = shadow.querySelector(".delete-output")
    const deleteStatus = shadow.querySelector(".delete-status")
    const deleteCancel = shadow.querySelector(".delete-cancel")
    const deleteClose = shadow.querySelector(".delete-close")
    const deletePrimary = shadow.querySelector(".delete-primary")
    let deleteTarget = null
    let deleteBusy = false
    let deleteReady = false
    let deleteRequest = 0

    const menuEl = shadow.querySelector(".menu")
    const menuCurrentTitle = shadow.querySelector(".menu-current-title")
    const menuCurrentMeta = shadow.querySelector(".menu-current-meta")
    const menuChannels = shadow.querySelector(".menu-channels")
    const starTitle = shadow.querySelector(".title-star")
    const starCurrent = shadow.querySelector(".menu-top .star-btn")
    const starButtons = [ starTitle, starCurrent ]
    const searchInput = shadow.querySelector(".menu-input")
    const menuFavSection = shadow.querySelector('[data-section="favorites"]')
    const menuAllSection = shadow.querySelector('[data-section="all"]')
    const menuFavList = shadow.querySelector('[data-list="favorites"]')
    const menuAllList = shadow.querySelector('[data-list="all"]')
    const menuAllHeading = menuAllSection.querySelector(".menu-heading")
    const menuEmpty = shadow.querySelector(".menu-empty")

    let index = -1

    function locate() {
      const here = normalizePath(location.pathname)
      let found = -1
      for (let i = 0; i < apps.length; i += 1) {
        if (normalizePath(entryPath(apps[i])) === here) {
          found = i
          break
        }
      }
      const exact = found >= 0
      if (found < 0) {
        let bestLength = -1
        for (let j = 0; j < apps.length; j += 1) {
          const candidate = normalizePath(entryPath(apps[j]))
          if (here.indexOf(candidate) === 0 && candidate.length > bestLength) {
            bestLength = candidate.length
            found = j
          }
        }
      }
      const pageTitle = (
        (scriptEl && scriptEl.getAttribute("data-ribbon-title")) ||
        document.title ||
        ""
      ).trim()
      return {
        index: found,
        title: exact && apps[found]
          ? apps[found].title
          : pageTitle || (apps[found] && apps[found].title) || "Untitled"
      }
    }

    const signals = meta.state && meta.state.assets ? meta.state.assets : {}
    let ribbonToken = meta.token || gitToken
    let canDelete = !!(meta.write && ribbonToken)
    let activeChannel = readChannel()
    let deckChannel = activeChannel
    let deck = []
    let deckCursor = 0
    let openedRecorded = false
    let appIndex = {}
    const storedDeck = readDeck()
    if (storedDeck && storedDeck.channel === activeChannel) {
      const known = {}
      for (let i = 0; i < apps.length; i += 1) known[bar.appKey(apps[i])] = true
      deck = (storedDeck.order || []).filter(function (key) {
        return known[key]
      })
      deckCursor = Number(storedDeck.cursor) || 0
      if (deckCursor >= deck.length) deckCursor = 0
    }
    let cardOpen = false
    let cardSwitch = 0

    const ui = bar.createBar({
      root: shadow,
      refs: {
        menuEl: menuEl,
        menuCurrentTitle: menuCurrentTitle,
        menuCurrentMeta: menuCurrentMeta,
        menuChannels: menuChannels,
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
      signals: signals,
      canDelete: canDelete,
      channel: { id: activeChannel, matches: channelMatches, label: channelLabel },
      getToken: function () { return ribbonToken },
      onSelect: function (app) { location.assign(absoluteUrl(app.url)) },
      onDelete: openDeletePanel,
      onChannel: function (id) {
        activeChannel = id || "all"
        saveChannel()
        deck = []
        deckChannel = activeChannel
        deckCursor = 0
      },
      beforeMenu: function () {
        renderChannels()
        if (refreshManifest) refreshManifest()
      }
    })

    // Tell the browser about the pages Back and Next would open, so a click
    // is a swap rather than a fresh load. The rules live in the page, not
    // the shadow root, and are replaced whenever the list changes.
    // Moderate, not immediate: immediate prerenders both neighbours (and their
    // manifests) before the user shows any intent, which costs two background
    // loads per navigation. Moderate waits for a hover or pointerdown, so a
    // deliberate Back/Next is still near-instant without the idle traffic.
    let speculationJson = ""
    function applySpeculation() {
      const urls = stale
        ? []
        : bar.neighborUrls(apps, index).map(function (url) {
          return absoluteUrl(url)
        })
      const json = urls.length
        ? JSON.stringify({
          prerender: [ { source: "list", urls: urls, eagerness: "moderate" } ]
        })
        : ""
      if (json === speculationJson) return
      speculationJson = json
      const old = document.getElementById("ribbon-speculation")
      if (old) old.remove()
      if (!json) return
      const script = document.createElement("script")
      script.type = "speculationrules"
      script.id = "ribbon-speculation"
      script.textContent = json
      ;(document.head || document.documentElement).appendChild(script)
    }

    function applyApps() {
      const current = locate()
      index = current.index
      appIndex = {}
      for (let i = 0; i < apps.length; i += 1) {
        appIndex[bar.appKey(apps[i])] = apps[i]
      }
      titleText.textContent = current.title
      titleButton.title = "Show all apps"
      menuCurrentTitle.textContent = current.title
      countEl.textContent = (index >= 0 ? bar.pad(index + 1, apps.length) : "—") +
        " / " + bar.pad(apps.length, apps.length)
      ui.setStale(stale)
      ui.setApps(apps)
      ui.setIndex(index)
      ui.setCanDelete(canDelete)
      ui.setChannel(activeChannel)
      ui.setGit(apps[index] && apps[index].git)
      ui.updateCurrentStar()
      ui.updateCurrentMeta()
      for (let k = 0; k < buttons.length; k += 1) {
        const act = buttons[k].getAttribute("data-act")
        if (act === "hide") continue
        const held = stale && (act === "prev" || act === "next" || act === "drift")
        buttons[k].disabled = held || apps.length < 2
      }
      contentsButton.disabled = !apps[index] || apps[index].kind !== "page"
      if (contentsButton.disabled) setCardOpen(false)
      if (ui.isMenuOpen()) {
        renderChannels()
        ui.renderMenu(searchInput.value)
      }
      if (window.__ribbon) window.__ribbon.apps = apps
      applySpeculation()
    }

    function setStale(next) {
      next = !!next
      if (stale === next) return
      stale = next
      applyApps()
    }

    applyApps()
    let manualHidden = readHidden()
    let autoHidden = manualHidden ? false : readScrolled()
    let topOffset = null
    const lastTargets = new Map()

    // The server reserves a strip at the top of the page, so the app's own
    // header is not covered before this file runs. Hiding the bar by hand
    // removes the strip too; the attribute also drives the bar's first paint.
    // The height comes from the host, so it cannot drift from the server.
    const barHeight = Number(host.getAttribute("data-ribbon-height")) || 0

    function setTopOffset(on, compensate) {
      if (topOffset === on) return
      const before = compensate ? scrollY() : 0
      host.toggleAttribute("data-ribbon-hidden", !on)
      topOffset = on
      if (!compensate || before === 0) return

      // Keep the page still when the strip is added or removed by hand.
      const after = on ? before + barHeight : Math.max(0, before - barHeight)
      if (after === before) return
      const root = document.documentElement
      const behavior = root.style.getPropertyValue("scroll-behavior")
      const priority = root.style.getPropertyPriority("scroll-behavior")
      root.style.setProperty("scroll-behavior", "auto", "important")
      window.scrollTo(0, after)
      if (behavior) root.style.setProperty("scroll-behavior", behavior, priority)
      else root.style.removeProperty("scroll-behavior")
    }

    function applyState() {
      const gone = manualHidden || autoHidden
      if (gone) {
        ui.closeTip()
        ui.closeMenu(false)
      }
      barEl.classList.toggle("is-gone", gone)
      if (gone) barEl.setAttribute("inert", "")
      else barEl.removeAttribute("inert")
      peekEl.classList.toggle("is-shown", manualHidden)
      peekEl.tabIndex = manualHidden ? 0 : -1
    }

    function setManual(hidden) {
      manualHidden = hidden
      if (hidden) autoHidden = false
      else lastTargets.clear()
      writeScrolled(autoHidden)
      setTopOffset(!hidden, true)
      try {
        sessionStorage.setItem(STORAGE_KEY, hidden ? "1" : "0")
      } catch (_) { /* storage may be unavailable */ }
      applyState()
    }

    function go(direction) {
      if (stale || apps.length < 2) return
      let target
      if (index < 0) {
        target = direction > 0 ? 0 : apps.length - 1
      } else {
        target = (index + direction + apps.length) % apps.length
        if (target === index) return
      }
      location.assign(absoluteUrl(apps[target].url))
    }

    function drift() {
      if (stale || apps.length < 2) return
      if (!ensureDeck()) return
      const current = bar.appKey(ui.currentApp())
      let key = deck[deckCursor]
      let guard = 0
      while (key === current && guard < deck.length) {
        deckCursor += 1
        if (deckCursor >= deck.length) deckCursor = 0
        key = deck[deckCursor]
        guard += 1
      }
      if (key === current) return
      deckCursor += 1
      if (deckCursor >= deck.length) {
        deck = buildDeck(activeChannel)
        deckChannel = activeChannel
        deckCursor = 0
      }
      saveDeck()
      const app = appByKey(key)
      if (app) location.assign(absoluteUrl(app.url))
    }

    function ensureDeck() {
      if (!deck.length || deckChannel !== activeChannel) {
        deck = buildDeck(activeChannel)
        deckChannel = activeChannel
        deckCursor = 0
        saveDeck()
      }
      return deck.length > 0
    }

    function buildDeck(channel) {
      const rng = seededRandom((Date.now() ^ (Math.random() * 4294967296)) >>> 0)
      const items = []
      for (let i = 0; i < apps.length; i += 1) {
        if (!channelMatches(apps[i], channel)) continue
        const weight = driftWeight(apps[i], rng)
        if (weight > 0) {
          items.push({ key: bar.appKey(apps[i]), weight: weight })
        }
      }
      const order = []
      while (items.length) {
        let total = 0
        for (let i = 0; i < items.length; i += 1) total += items[i].weight
        let pick = rng() * total
        let at = 0
        for (; at < items.length; at += 1) {
          pick -= items[at].weight
          if (pick <= 0) break
        }
        if (at >= items.length) at = items.length - 1
        order.push(items[at].key)
        items.splice(at, 1)
      }
      return order
    }

    function seededRandom(seed) {
      let value = seed >>> 0
      return function () {
        value += 0x6d2b79f5
        let t = value
        t = Math.imul(t ^ (t >>> 15), t | 1)
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
      }
    }

    function driftWeight(app, rng) {
      const key = bar.appKey(app)
      const entry = signals[key] || {}
      const git = app.git || {}
      const state = git.state || ""
      let weight = 1
      if (!git.repo) weight += 2.4
      else if (state === "conflicted") weight += 2.6
      // `state` is one word for the whole repo, so a branch fact such as
      // "behind" or "detached" hides uncommitted work. Read `dirty` itself.
      else if (git.dirty) weight += 2
      else if (state === "ahead" || state === "diverged") weight += 2.2
      else if (state === "no-upstream" || state === "no-commits") weight += 1.6
      else if (state === "clean") weight += 0.2
      if (ui.isFavorite(app)) weight += 1.2
      const openedAt = entry.last_opened ? Date.parse(entry.last_opened) : 0
      const touched = Math.max((Number(app.mtime) || 0) * 1000, openedAt || 0)
      const days = touched ? Math.max(0, (Date.now() - touched) / 86400000) : 365
      weight += Math.min(days / 45, 2.5)
      if (!entry.last_opened) weight += 1.2
      if (entry.opens) weight -= Math.min(entry.opens * 0.08, 0.8)
      weight += rng() * 0.5
      return Math.max(0.15, weight)
    }

    function channelMatches(app, channel) {
      if (!channel || channel === "all") return true
      const git = app.git || {}
      const state = git.state || ""
      if (channel === "needs-push") {
        return !!git.repo && (
          Number(git.ahead) > 0 ||
          state === "diverged" ||
          (!!git.has_remote && state === "no-upstream")
        )
      }
      if (channel === "dirty") return !!git.repo && !!git.dirty
      if (channel === "no-repo") return !git.repo
      if (channel === "shipped") return state === "clean" && !!git.has_remote
      if (channel === "dusty") return isDusty(app)
      if (channel.indexOf("type:") === 0) {
        return String(app.type || "").toLowerCase() === channel.slice(5)
      }
      return true
    }

    function channelLabel(channel) {
      if (channel === "all") return "All apps"
      if (channel === "needs-push") return "Needs push"
      if (channel === "dirty") return "Uncommitted"
      if (channel === "no-repo") return "No repo"
      if (channel === "shipped") return "Shipped"
      if (channel === "dusty") return "Dusty"
      if (channel.indexOf("type:") === 0) {
        const wanted = channel.slice(5)
        for (let i = 0; i < apps.length; i += 1) {
          if (String(apps[i].type || "").toLowerCase() === wanted) {
            return apps[i].type
          }
        }
        return wanted
      }
      return channel
    }

    function isDusty(app) {
      const entry = signals[bar.appKey(app)] || {}
      if (!entry.last_opened) return true
      const opened = Date.parse(entry.last_opened)
      return !opened || Date.now() - opened > 30 * 86400000
    }

    function appByKey(key) {
      return appIndex[key] || null
    }

    function saveDeck() {
      try {
        sessionStorage.setItem(DECK_KEY, JSON.stringify({
          channel: deckChannel,
          order: deck,
          cursor: deckCursor
        }))
      } catch (_) { /* storage may be unavailable */ }
    }

    function saveChannel() {
      try {
        sessionStorage.setItem(CHANNEL_KEY, activeChannel)
      } catch (_) { /* storage may be unavailable */ }
    }

    function reloadApp() {
      ui.closeMenu(false)
      location.reload()
    }

    function cardAddress(app) {
      const parts = String(app && app.path ? app.path : "")
        .split("/")
        .filter(function (part) { return !!part })
        .map(function (part) { return encodeURIComponent(part) })
      const address = new URL(
        "card/" + (parts.length ? parts.join("/") + "/" : ""),
        scriptBase
      )
      address.searchParams.set("embed", "1")
      return address.href
    }

    function motionReduced() {
      return !!(window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches)
    }

    function cancelCardAnimations() {
      if (!cardFrame.getAnimations) return
      cardFrame.getAnimations().forEach(function (animation) {
        animation.cancel()
      })
    }

    function animateCardIn() {
      if (!cardFrame.animate || motionReduced()) return
      const entering = cardFrame.animate(
        [
          { transform: "perspective(1600px) rotateY(90deg)", opacity: 0 },
          { transform: "perspective(1600px) rotateY(0deg)", opacity: 1 }
        ],
        { duration: 260, easing: "cubic-bezier(.2, .7, .3, 1)" }
      )
      window.setTimeout(function () {
        if (entering.playState !== "finished") entering.cancel()
      }, 420)
    }

    function animateCardOut(done) {
      if (!cardFrame.animate || motionReduced()) {
        done()
        return
      }
      let finished = false
      const finish = function () {
        if (finished) return
        finished = true
        done()
      }
      const out = cardFrame.animate(
        [
          { transform: "perspective(1600px) rotateY(0deg)", opacity: 1 },
          { transform: "perspective(1600px) rotateY(-90deg)", opacity: 0 }
        ],
        {
          duration: 200,
          easing: "cubic-bezier(.45, 0, .55, 1)",
          fill: "forwards"
        }
      )
      window.setTimeout(finish, 320)
      out.finished.then(finish).catch(finish)
    }

    function setCardOpen(open) {
      const app = ui.currentApp()
      if (open) {
        if (!app || app.kind !== "page" || cardOpen) return
        cardOpen = true
        cardSwitch += 1
        cancelCardAnimations()
        cardFrame.title = (app.title ? app.title + " " : "") + "contents"
        cardFrame.src = cardAddress(app)
        cardOverlay.hidden = false
        contentsButton.classList.add("is-active")
        contentsButton.setAttribute("aria-pressed", "true")
        contentsButton.setAttribute("aria-label", "Hide contents")
        contentsButton.title = "Hide contents — C"
        animateCardIn()
        try { cardFrame.focus() } catch (_) { /* ignore */ }
        return
      }
      if (!cardOpen) return
      cardOpen = false
      contentsButton.classList.remove("is-active")
      contentsButton.setAttribute("aria-pressed", "false")
      contentsButton.setAttribute("aria-label", "Show contents")
      contentsButton.title = "Show contents — C"
      const serial = cardSwitch + 1
      cardSwitch = serial
      animateCardOut(function () {
        if (serial !== cardSwitch) return
        cancelCardAnimations()
        cardOverlay.hidden = true
        cardFrame.removeAttribute("src")
        try { contentsButton.focus() } catch (_) { /* ignore */ }
      })
    }

    function mergeSignals(incoming) {
      if (!incoming) return
      Object.keys(incoming).forEach(function (key) {
        const mine = signals[key]
        const theirs = incoming[key]
        if (!mine) {
          signals[key] = theirs
          return
        }
        const mineAt = Date.parse(mine.updated || "") || 0
        const theirAt = Date.parse(theirs.updated || "") || 0
        if (theirAt >= mineAt) signals[key] = theirs
      })
    }

    function recordOpen() {
      // A prerendered page is not a visit. Count it when the reader lands.
      if (document.prerendering) {
        document.addEventListener("prerenderingchange", function () {
          recordOpen()
        }, { once: true })
        return
      }
      const app = ui.currentApp()
      if (!app) return
      const key = bar.appKey(app)
      const entry = Object.assign({}, signals[key] || {})
      const now = new Date()
      entry.opens = (Number(entry.opens) || 0) + 1
      entry.last_opened = now.toISOString()
      entry.updated = now.toISOString()
      signals[key] = entry
      ui.updateCurrentMeta()
      if (ui.isMenuOpen()) {
        renderChannels()
        ui.renderMenu(searchInput.value)
      }
      if (!ribbonToken) return
      fetch(new URL("signal", scriptBase).href, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Ribbon-Token": ribbonToken
        },
        body: JSON.stringify({ path: key, signal: "open" })
      })
        .then(function (response) {
          return response.json()
        })
        .then(function (data) {
          if (!data || !data.ok || !data.state || !data.state.assets) return
          mergeSignals(data.state.assets)
          ui.updateCurrentMeta()
          if (ui.isMenuOpen()) {
            renderChannels()
            ui.renderMenu(searchInput.value)
          }
        })
        .catch(function () { /* the local record stands */ })
    }

    function buildChannels() {
      const list = [ { id: "all", label: "All", count: apps.length } ]
      const add = function (id, label) {
        let count = 0
        for (let i = 0; i < apps.length; i += 1) {
          if (channelMatches(apps[i], id)) count += 1
        }
        if (count) {
          list.push({
            id: id,
            label: label || channelLabel(id),
            count: count
          })
        }
      }
      add("needs-push")
      add("dirty")
      add("no-repo")
      add("dusty")
      add("shipped")
      const types = []
      for (let i = 0; i < apps.length; i += 1) {
        const type = String(apps[i].type || "").trim()
        if (type && types.indexOf(type) === -1) types.push(type)
      }
      types.sort(function (a, b) { return a.localeCompare(b) })
      for (let i = 0; i < types.length; i += 1) {
        add("type:" + types[i].toLowerCase(), types[i])
      }
      return list
    }

    function renderChannels() {
      const list = buildChannels()
      let active = false
      for (let i = 0; i < list.length; i += 1) {
        if (list[i].id === activeChannel) active = true
      }
      if (!active) {
        activeChannel = "all"
        saveChannel()
      }
      ui.setChannel(activeChannel)
      menuChannels.textContent = ""
      list.forEach(function (channel) {
        const chip = document.createElement("button")
        chip.type = "button"
        chip.className = "chip"
        chip.setAttribute("data-channel", channel.id)
        chip.setAttribute(
          "aria-pressed",
          channel.id === activeChannel ? "true" : "false"
        )
        chip.title = "Drift inside " + channel.label.toLowerCase()
        chip.appendChild(document.createTextNode(channel.label))
        const count = document.createElement("span")
        count.className = "chip-count"
        count.textContent = String(channel.count)
        chip.appendChild(count)
        menuChannels.appendChild(chip)
      })
    }

    function removeDeletedApp(app) {
      const key = bar.appKey(app)
      apps = apps.filter(function (item) {
        return bar.appKey(item) !== key
      })
      ui.removeFavorite(app)
      if (signals[key]) delete signals[key]
      deck = deck.filter(function (item) { return item !== key })
      if (deckCursor > deck.length) deckCursor = 0
      saveDeck()
      writeCachedApps(apps)
      applyApps()
    }

    function setDeleteBusy(busy) {
      deleteBusy = busy
      deletePrimary.disabled = busy || !deleteReady
      deleteCancel.disabled = busy
      deleteClose.disabled = busy
      deletePrimary.textContent = busy ? "Deleting…" : "Delete folder"
    }

    function resetDeletePanel(app) {
      deleteTarget = app
      deleteReady = false
      deleteOverlay.hidden = false
      deleteTitle.textContent = app.title || bar.appKey(app)
      deletePath.textContent = "/" + (app.path || app.dir || "")
      deleteCommand.textContent = "Working out the command…"
      deleteOutput.hidden = true
      deleteOutput.textContent = ""
      deleteStatus.className = "delete-status"
      deleteStatus.textContent = ""
      setDeleteBusy(false)
    }

    function closeDeletePanel(reopen) {
      if (deleteBusy) return
      deleteRequest += 1
      deleteTarget = null
      deleteReady = false
      deleteOverlay.hidden = true
      deleteStatus.textContent = ""
      if (reopen && apps.length) ui.openMenu()
    }

    function showDeleteError(data) {
      const error = (data && (data.error || data.message)) || "The folder could not be deleted."
      const output = (data && data.output) || ""
      deleteStatus.className = "delete-status is-bad"
      deleteStatus.textContent = error.split("\n")[0].slice(0, 140)
      deleteOutput.textContent = output
      deleteOutput.hidden = !output
    }

    function openDeletePanel(app) {
      if (!canDelete || !app) return
      const dir = app.path || app.dir || ""
      if (!dir || dir === ".") return
      ui.closeMenu(false)
      resetDeletePanel(app)
      const request = ++deleteRequest
      deleteCancel.focus()

      fetch("/__ribbon/delete.json?dir=" + encodeURIComponent(dir), {
        cache: "no-store",
        headers: { "X-Ribbon-Token": ribbonToken }
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
          if (request !== deleteRequest || deleteTarget !== app) return
          if (!data || !data.ok || !data.command) {
            deleteCommand.textContent = "—"
            showDeleteError(data)
            return
          }
          deleteCommand.textContent = data.command
          deletePath.textContent = data.path || ("/" + dir)
          deleteReady = true
          setDeleteBusy(false)
          deletePrimary.focus()
        })
        .catch(function (error) {
          if (request !== deleteRequest) return
          deleteCommand.textContent = "—"
          showDeleteError({ error: error.message || "Could not prepare the delete." })
        })
    }

    function confirmDelete() {
      if (!deleteTarget || deleteBusy || !deleteReady) return
      const app = deleteTarget
      const key = bar.appKey(app)
      const dir = app.path || app.dir || ""
      const wasCurrent = index >= 0 && bar.appKey(apps[index]) === key
      const fallback = apps.filter(function (item) {
        return bar.appKey(item) !== key
      })[0] || null

      setDeleteBusy(true)
      deleteStatus.className = "delete-status"
      deleteStatus.textContent = "Running the command…"
      deleteOutput.hidden = true
      deleteOutput.textContent = ""

      fetch("/__ribbon/delete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Ribbon-Token": ribbonToken
        },
        body: JSON.stringify({ dir: dir })
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
            setDeleteBusy(false)
            showDeleteError(data)
            return
          }
          deleteBusy = false
          deleteRequest += 1
          deleteOverlay.hidden = true
          deleteTarget = null
          deleteReady = false
          removeDeletedApp(app)
          if (wasCurrent) {
            location.assign(fallback ? absoluteUrl(fallback.url) : absoluteUrl("/"))
          } else {
            ui.openMenu()
          }
        })
        .catch(function (error) {
          setDeleteBusy(false)
          showDeleteError({ error: error.message || "The request failed." })
        })
    }

    shadow.addEventListener("click", function (event) {
      const button = event.target && event.target.closest
        ? event.target.closest("button[data-act]")
        : null
      if (!button) return
      const action = button.getAttribute("data-act")
      if (action === "prev") go(-1)
      else if (action === "next") go(1)
      else if (action === "contents") setCardOpen(!cardOpen)
      else if (action === "drift") drift()
      else if (action === "reload") reloadApp()
      else if (action === "hide") setManual(true)
    })
    cardClose.addEventListener("click", function () {
      setCardOpen(false)
    })
    cardFrame.addEventListener("load", function () {
      if (!cardOpen) return
      try {
        const view = cardFrame.contentWindow
        if (!view) return
        view.addEventListener("keydown", function (event) {
          if (event.key !== "Escape") return
          event.preventDefault()
          setCardOpen(false)
        })
      } catch (_) { /* cross-origin, leave the close button */ }
    })
    peekEl.addEventListener("click", function () {
      setManual(false)
    })

    document.addEventListener("pointerdown", function (event) {
      const path = event.composedPath ? event.composedPath() : []
      if (path.indexOf(menuEl) !== -1 || path.indexOf(titleButton) !== -1) return
      ui.closeMenu(false)
    }, true)

    deleteCancel.addEventListener("click", function () {
      closeDeletePanel(true)
    })
    deleteClose.addEventListener("click", function () {
      closeDeletePanel(true)
    })
    deletePrimary.addEventListener("click", confirmDelete)
    deleteOverlay.addEventListener("pointerdown", function (event) {
      if (event.target === deleteOverlay) closeDeletePanel(true)
    })
    deleteOverlay.addEventListener("keydown", function (event) {
      if (bar.trapTab(event, deleteOverlay)) return
      if (event.key === "Escape") {
        event.preventDefault()
        closeDeletePanel(true)
      }
    })
    let pending = null
    function processScroll() {
      const event = pending
      pending = null
      if (manualHidden) return
      if (event && event.target && menuEl.contains(event.target)) return

      let target = event && event.target
      if (
        target === document ||
        target === window ||
        target === document.documentElement ||
        target === document.body
      ) {
        target = null
      }
      const y = target ? target.scrollTop : scrollY()
      const hasPrevious = lastTargets.has(target)
      const previous = hasPrevious ? lastTargets.get(target) : y
      const delta = y - previous

      if (Math.abs(delta) < 10) {
        if (!hasPrevious) lastTargets.set(target, y)
        return
      }

      if (y <= 8) autoHidden = false
      else if (delta > 0 && y > 48) autoHidden = true
      else if (delta < 0) autoHidden = false

      lastTargets.set(target, y)
      if (!target) writeScrolled(autoHidden)
      applyState()
    }

    function onScroll(event) {
      if (pending) return
      pending = event
      requestAnimationFrame(processScroll)
    }

    window.addEventListener("keydown", function (event) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target
      if (
        target &&
        (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
      ) {
        return
      }

      const key = event.key
      if (!deleteOverlay.hidden) {
        if (key === "Escape") {
          closeDeletePanel(true)
          event.preventDefault()
          event.stopPropagation()
        }
        return
      }
      if (!gitOverlay.hidden) {
        if (key === "Escape") {
          ui.closeGitPanel()
          event.preventDefault()
          event.stopPropagation()
        }
        return
      }
      if (cardOpen) {
        if (key === "Escape" || key === "c" || key === "C") {
          setCardOpen(false)
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
      if (key === "[") go(-1)
      else if (key === "]") go(1)
      else if (key === "c" || key === "C") setCardOpen(true)
      else if (key === "r" || key === "R") {
        if (event.shiftKey) reloadApp()
        else drift()
      } else if (key === "h" || key === "H") toggleHidden()
      else handled = false

      if (handled) {
        event.preventDefault()
        event.stopPropagation()
      }
    }, true)

    function toggleHidden() {
      if (!manualHidden && autoHidden) {
        autoHidden = false
        writeScrolled(false)
        applyState()
        return
      }
      setManual(!manualHidden)
    }

    window.addEventListener("scroll", onScroll, { passive: true })
    document.addEventListener("scroll", onScroll, { passive: true, capture: true })

    window.__ribbon = {
      show: function () { setManual(false) },
      hide: function () { setManual(true) },
      toggle: function () { toggleHidden() },
      prev: function () { go(-1) },
      next: function () { go(1) },
      drift: drift,
      random: drift,
      contents: function (on) {
        setCardOpen(arguments.length ? !!on : !cardOpen)
      },
      channel: function () { return activeChannel },
      apps: apps
    }

    function update(nextApps, nextMeta) {
      const next = nextApps.filter(function (app) {
        return app && typeof app.url === "string" && app.url
      })
      if (!next.length) return
      apps = next
      stale = false
      if (nextMeta) {
        if (nextMeta.token) ribbonToken = nextMeta.token
        if (typeof nextMeta.write === "boolean") {
          canDelete = !!(nextMeta.write && ribbonToken)
        }
        if (nextMeta.state && nextMeta.state.assets) {
          mergeSignals(nextMeta.state.assets)
        }
      }
      applyApps()
      if (!openedRecorded) {
        openedRecorded = true
        if (ui.currentApp()) recordOpen()
      }
    }

    setTopOffset(!manualHidden, false)
    applyState()
    // The boot script hid the shell before this file ran. From here the
    // is-gone/is-shown classes own the state; the hidden attribute stays so
    // the offset matches the bar while the bar is hidden by hand.
    host.removeAttribute("data-ribbon-scrolled")
    if (!openedRecorded) {
      openedRecorded = true
      if (ui.currentApp()) recordOpen()
    }
    return {
      update: update,
      setStale: setStale
    }
  }

  function normalizePath(path) {
    let value = path
    try {
      value = decodeURIComponent(path)
    } catch (_) { /* use the path as given */ }
    value = value.replace(/\/index\.html?$/i, "/")
    if (value.charAt(value.length - 1) !== "/" && !/\.[a-z0-9]+$/i.test(value)) {
      value += "/"
    }
    return value
  }

  function entryPath(app) {
    try {
      return new URL(app.url, scriptBase).pathname
    } catch (_) {
      return app.url
    }
  }

  function readHidden() {
    try {
      return sessionStorage.getItem(STORAGE_KEY) === "1"
    } catch (_) {
      return false
    }
  }

  // The scroll-hidden state belongs to one page, unlike the manual hide. Store
  // the page it belongs to so a new app opens with the bar visible.
  function readScrolled() {
    try {
      return sessionStorage.getItem(SCROLL_KEY) === location.href
    } catch (_) {
      return false
    }
  }

  function writeScrolled(hidden) {
    try {
      if (hidden) sessionStorage.setItem(SCROLL_KEY, location.href)
      else sessionStorage.removeItem(SCROLL_KEY)
    } catch (_) { /* storage may be unavailable */ }
  }

  function readChannel() {
    try {
      return sessionStorage.getItem(CHANNEL_KEY) || "all"
    } catch (_) {
      return "all"
    }
  }

  function readDeck() {
    try {
      const data = JSON.parse(sessionStorage.getItem(DECK_KEY) || "null")
      if (!data || !Array.isArray(data.order)) return null
      return data
    } catch (_) {
      return null
    }
  }

  function scrollY() {
    return window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0
  }

  boot()
})()

/* Ribbon bar — shared pure helpers.
 *
 * Loaded before either host (ribbon.js or shell.js). No DOM, no state.
 * Everything here is exposed through window.__RIBBON_BAR__.
 */
(function () {
  "use strict"

  const LED_WORK = { ok: 0, warn: 1, bad: 2, off: 3 }

  function appKey(app) {
    return app ? app.dir || app.path || app.url || "" : ""
  }

  function pad(number, total) {
    const width = String(total).length
    let value = String(number)
    while (value.length < width) value = "0" + value
    return value
  }

  function matchesQuery(app, query) {
    if (!query) return true
    const haystack = String(app.title || "").toLowerCase() +
      " " + String(app.path || app.dir || "").toLowerCase() +
      " " + String(app.type || "").toLowerCase()
    return haystack.indexOf(query) !== -1
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

  function defaultRepoName(app) {
    const path = app ? app.path || app.dir || app.url || "" : ""
    let name = path.split("/").filter(Boolean).pop() || (app && app.title) || "app"
    name = name.replace(/^\d{4}-\d{2}-\d{2}-/, "")
    name = name.replace(/\.html?$/i, "")
    name = name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "")
    return (name || "app").slice(0, 100)
  }

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

  function isParked(entry) {
    return !!(
      entry &&
      entry.parked_until &&
      Date.parse(entry.parked_until) > Date.now()
    )
  }

  function createBar(options) {
    options = options || {}
    const root = options.root
    const doc = root.ownerDocument || root
    const refs = options.refs || {}
    const signals = options.signals || {}
    const channel = options.channel || {
      id: "all",
      matches: function () { return true },
      label: function () { return "All apps" }
    }
    let apps = Array.isArray(options.apps) ? options.apps : []
    let index = typeof options.index === "number" ? options.index : -1
    let canDelete = !!options.canDelete
    let channelId = channel.id || "all"
    const favorites = readFavorites()
    let menuOpen = false

    function readFavorites() {
      try {
        const stored = JSON.parse(localStorage.getItem("ribbon:favorites") || "[]")
        if (Array.isArray(stored)) {
          return new Set(stored.filter(function (item) {
            return typeof item === "string"
          }))
        }
      } catch (_) { /* ignore unreadable favorites */ }
      return new Set()
    }

    function saveFavorites() {
      try {
        localStorage.setItem("ribbon:favorites", JSON.stringify(Array.from(favorites)))
      } catch (_) { /* storage may be unavailable */ }
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
      const starButtons = refs.starButtons || []
      for (let i = 0; i < starButtons.length; i += 1) {
        const button = starButtons[i]
        button.disabled = !app
        button.setAttribute("aria-pressed", favorite ? "true" : "false")
        button.textContent = favorite ? "★" : "☆"
        button.title = label
        button.setAttribute("aria-label", label)
      }
    }

    function relativeTime(value) {
      const at = typeof value === "number" ? value : Date.parse(value)
      if (!at) return "never"
      const minutes = Math.round((Date.now() - at) / 60000)
      if (minutes < 1) return "just now"
      if (minutes < 60) return minutes + "m ago"
      const hours = Math.round(minutes / 60)
      if (hours < 24) return hours + "h ago"
      const days = Math.round(hours / 24)
      if (days < 30) return days + "d ago"
      return Math.round(days / 30) + "mo ago"
    }

    function updateCurrentMeta() {
      const app = currentApp()
      const entry = app ? signals[appKey(app)] || {} : {}
      const bits = []
      if (app) {
        if (entry.last_opened) {
          bits.push("opened " + relativeTime(entry.last_opened))
        } else {
          bits.push("never opened")
        }
        if (app.mtime) bits.push("touched " + relativeTime(app.mtime * 1000))
        if (entry.opens) {
          bits.push(entry.opens + (entry.opens === 1 ? " open" : " opens"))
        }
        if (entry.keep) bits.push("kept")
        if (isParked(entry)) bits.push("parked")
      }
      if (refs.menuCurrentMeta) {
        refs.menuCurrentMeta.textContent = bits.join(" · ")
      }
      const keep = !!entry.keep
      const park = isParked(entry)
      if (refs.keepButton) {
        refs.keepButton.disabled = !app
        refs.keepButton.setAttribute("aria-pressed", keep ? "true" : "false")
        refs.keepButton.textContent = keep ? "Kept" : "Keep"
      }
      if (refs.parkButton) {
        refs.parkButton.disabled = !app
        refs.parkButton.setAttribute("aria-pressed", park ? "true" : "false")
        refs.parkButton.textContent = park ? "Parked" : "Park"
      }
    }

    function setChannel(id) {
      channelId = id || "all"
    }

    function menuLights(git) {
      const lights = gitLights(git)
      const classes = [ lights.repoClass, lights.changesClass, lights.remoteClass ]
      const wrap = doc.createElement("span")
      wrap.className = "menu-leds"
      wrap.setAttribute("role", "img")
      for (let i = 0; i < classes.length; i += 1) {
        const dot = doc.createElement("span")
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
      const row = doc.createElement("div")
      row.className = "menu-row" + (appIndex === index ? " is-current" : "")

      const open = doc.createElement("button")
      open.type = "button"
      open.className = "menu-app"
      open.setAttribute("data-app", String(appIndex))
      if (appIndex === index) open.setAttribute("aria-current", "true")

      const title = doc.createElement("span")
      title.className = "menu-app-title"
      if (app.icon) {
        const glyph = doc.createElement("span")
        glyph.className = "menu-app-glyph"
        glyph.textContent = app.icon
        glyph.title = app.type || "Project"
        glyph.setAttribute("aria-hidden", "true")
        if (app.color) glyph.style.color = app.color
        title.appendChild(glyph)
      }
      title.appendChild(doc.createTextNode(app.title || "Untitled"))
      const entry = signals[appKey(app)] || {}
      if (entry.keep || isParked(entry)) {
        const flag = doc.createElement("span")
        flag.className = "menu-app-flag"
        flag.textContent = isParked(entry) ? "parked" : "kept"
        title.appendChild(flag)
      }

      const path = app.path || app.dir || ""
      const dir = doc.createElement("span")
      dir.className = "menu-app-dir"
      dir.textContent = path && path !== "." ? "/" + path : "/"

      open.appendChild(title)
      open.appendChild(dir)

      const star = doc.createElement("button")
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
      if (canDelete) {
        const remove = doc.createElement("button")
        remove.type = "button"
        remove.className = "row-delete"
        remove.setAttribute("data-delete", appKey(app))
        remove.setAttribute("aria-haspopup", "dialog")
        remove.title = "Delete this folder…"
        remove.setAttribute(
          "aria-label",
          "Delete " + (app.title || appKey(app)) + " folder"
        )
        remove.textContent = "✕"
        row.appendChild(remove)
      }
      return row
    }

    function renderMenu(query) {
      const needle = (query == null ? refs.searchInput.value : query).trim().toLowerCase()
      refs.menuFavList.textContent = ""
      refs.menuAllList.textContent = ""
      let favoriteCount = 0
      let otherCount = 0
      const rows = []

      apps.forEach(function (app, appIndex) {
        if (!channel.matches(app, channelId)) return
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
          refs.menuFavList.appendChild(favoriteRow(app, appIndex))
          favoriteCount += 1
        } else {
          refs.menuAllList.appendChild(favoriteRow(app, appIndex))
          otherCount += 1
        }
      })

      refs.menuFavSection.hidden = favoriteCount === 0
      refs.menuAllSection.hidden = otherCount === 0
      refs.menuEmpty.hidden = favoriteCount + otherCount > 0
      refs.menuEmpty.textContent = channelId === "all"
        ? "No apps match."
        : "Nothing in this channel."
      if (channelId === "all") {
        refs.menuAllHeading.textContent = favoriteCount ? "Other apps" : "All apps"
      } else {
        refs.menuAllHeading.textContent = channel.label(channelId)
      }
    }

    function openMenu() {
      if (!apps.length) return
      if (menuOpen) {
        refs.searchInput.focus()
        refs.searchInput.select()
        return
      }
      menuOpen = true
      refs.menuEl.hidden = false
      refs.titleButton.setAttribute("aria-expanded", "true")
      refs.searchInput.value = ""
      if (options.beforeMenu) options.beforeMenu()
      renderMenu("")
      updateCurrentStar()
      updateCurrentMeta()
      requestAnimationFrame(function () {
        refs.searchInput.focus()
        refs.searchInput.select()
      })
    }

    function closeMenu(returnFocus) {
      if (!menuOpen) return
      menuOpen = false
      refs.menuEl.hidden = true
      refs.titleButton.setAttribute("aria-expanded", "false")
      if (returnFocus) refs.titleButton.focus()
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
      if (menuOpen) renderMenu()
      updateCurrentStar()
      if (focusStar) {
        const stars = refs.menuEl.querySelectorAll("[data-star]")
        for (let i = 0; i < stars.length; i += 1) {
          if (stars[i].getAttribute("data-star") === key) {
            stars[i].focus()
            break
          }
        }
      }
    }

    function removeFavorite(app) {
      if (!app) return
      favorites.delete(appKey(app))
      saveFavorites()
    }

    function selectRow(row) {
      if (!row || !options.onSelect) return
      const app = apps[Number(row.getAttribute("data-app"))]
      if (app) options.onSelect(app, apps.indexOf(app))
    }

    refs.titleButton.addEventListener("click", toggleMenu)
    const starButtons = refs.starButtons || []
    for (let i = 0; i < starButtons.length; i += 1) {
      starButtons[i].addEventListener("click", function () {
        const app = currentApp()
        if (app) toggleFavorite(app, false)
        this.focus()
      })
    }
    refs.searchInput.addEventListener("input", function () {
      renderMenu(refs.searchInput.value)
    })
    refs.searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault()
        closeMenu(true)
        return
      }
      if (event.key === "Enter") {
        const first = refs.menuEl.querySelector(".menu-app")
        if (first) {
          event.preventDefault()
          selectRow(first)
        }
        return
      }
      if (event.key === "ArrowDown") {
        const first = refs.menuEl.querySelector(".menu-app")
        if (first) {
          event.preventDefault()
          first.focus()
        }
      }
    })
    refs.menuEl.addEventListener("click", function (event) {
      const target = event.target && event.target.closest
        ? event.target
        : null
      if (!target) return

      const remove = target.closest(".row-delete")
      if (remove) {
        const key = remove.getAttribute("data-delete")
        for (let i = 0; i < apps.length; i += 1) {
          if (appKey(apps[i]) === key) {
            if (options.onDelete) options.onDelete(apps[i])
            break
          }
        }
        return
      }

      const star = target.closest(".row-star")
      if (star) {
        for (let i = 0; i < apps.length; i += 1) {
          if (appKey(apps[i]) === star.getAttribute("data-star")) {
            toggleFavorite(apps[i], true)
            break
          }
        }
        return
      }

      const row = target.closest(".menu-app")
      if (row) selectRow(row)
    })

    if (refs.menuChannels) {
      refs.menuChannels.addEventListener("click", function (event) {
        const chip = event.target && event.target.closest
          ? event.target.closest("[data-channel]")
          : null
        if (!chip) return
        const id = chip.getAttribute("data-channel") || "all"
        setChannel(id)
        if (options.onChannel) options.onChannel(id)
        if (options.beforeMenu) options.beforeMenu()
        renderMenu()
        if (refs.searchInput) refs.searchInput.focus()
      })
    }

    if (refs.keepButton && options.onSignal) {
      refs.keepButton.addEventListener("click", function () {
        const app = currentApp()
        if (!app) return
        const entry = signals[appKey(app)] || {}
        options.onSignal("keep", !entry.keep)
      })
    }

    if (refs.parkButton && options.onSignal) {
      refs.parkButton.addEventListener("click", function () {
        const app = currentApp()
        if (!app) return
        const entry = signals[appKey(app)] || {}
        options.onSignal("park", !isParked(entry))
      })
    }

    return {
      setApps: function (next) {
        apps = Array.isArray(next) ? next : []
        if (menuOpen) renderMenu()
      },
      setIndex: function (next) {
        index = typeof next === "number" ? next : -1
      },
      setCanDelete: function (next) {
        canDelete = !!next
      },
      setChannel: setChannel,
      setToken: function () { /* the git panel arrives in a later packet */ },
      currentApp: currentApp,
      appKey: appKey,
      isFavorite: isFavorite,
      updateCurrentStar: updateCurrentStar,
      updateCurrentMeta: updateCurrentMeta,
      renderMenu: renderMenu,
      openMenu: openMenu,
      closeMenu: closeMenu,
      toggleMenu: toggleMenu,
      toggleFavorite: toggleFavorite,
      removeFavorite: removeFavorite,
      isMenuOpen: function () { return menuOpen },
      setGit: function () { /* the LEDs arrive in a later packet */ },
      gitLights: gitLights,
      gitWorkRank: gitWorkRank
    }
  }

  window.__RIBBON_BAR__ = {
    appKey: appKey,
    pad: pad,
    matchesQuery: matchesQuery,
    escapeAttribute: escapeAttribute,
    defaultRepoName: defaultRepoName,
    gitLights: gitLights,
    gitWorkRank: gitWorkRank,
    decideGitAction: decideGitAction,
    repoTip: repoTip,
    changesTip: changesTip,
    remoteTip: remoteTip,
    isParked: isParked,
    createBar: createBar
  }
})()

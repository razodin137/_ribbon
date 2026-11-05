/* Ribbon bar — the shared bar: pure helpers plus createBar.
 *
 * Loaded before the host (ribbon.js). The pure layer has no DOM or state;
 * createBar owns the bar's shared state and DOM events. Everything here is
 * exposed through window.__RIBBON_BAR__.
 */
(function () {
  "use strict"

  const LED_WORK = { ok: 0, warn: 1, bad: 2, off: 3 }

  function appKey(app) {
    return app ? app.dir || app.path || app.url || "" : ""
  }

  // The URLs Back and Next would open, in the order the bar would go. With
  // two apps the same neighbour sits on both sides, so keep it once.
  function neighborUrls(apps, index) {
    if (!Array.isArray(apps) || apps.length < 2) return []
    const urls = []
    const add = function (app) {
      const url = app && app.url
      if (typeof url === "string" && url && urls.indexOf(url) === -1) {
        urls.push(url)
      }
    }
    if (typeof index !== "number" || index < 0) {
      add(apps[apps.length - 1])
      add(apps[0])
      return urls
    }
    if (index >= apps.length) return []
    add(apps[(index - 1 + apps.length) % apps.length])
    add(apps[(index + 1) % apps.length])
    return urls
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
    let stale = false
    let tipPinned = false
    let tipTimer = 0
    let tipIsOpen = false
    let gitToken = ""
    let gitDetail = null
    let gitAction = null
    let gitBusy = false
    let gitBlocked = false
    let gitReturnFocus = null
    const hoverCapable = !!(window.matchMedia && window.matchMedia("(hover: hover)").matches)

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
      }
      if (refs.menuCurrentMeta) {
        refs.menuCurrentMeta.textContent = bits.join(" · ")
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
      row.className = "menu-row" + (appIndex === index ? " is-current" : "") +
        (stale ? " is-stale" : "")

      const open = doc.createElement("button")
      open.type = "button"
      open.className = "menu-app"
      open.setAttribute("data-app", String(appIndex))
      if (appIndex === index) open.setAttribute("aria-current", "true")
      if (stale) {
        open.disabled = true
        open.title = "Refreshing the app list…"
      }

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

    function setLedLabel(name, text, hint) {
      const ledButtons = refs.ledButtons || []
      for (let i = 0; i < ledButtons.length; i += 1) {
        if (ledButtons[i].getAttribute("data-led") === name) {
          ledButtons[i].setAttribute("aria-label", text + ". " + hint)
          return
        }
      }
    }

    function setGit(git) {
      const lights = gitLights(git)

      refs.ledRepo.className = "led " + lights.repoClass
      refs.ledChanges.className = "led " + lights.changesClass
      refs.ledRemote.className = "led " + lights.remoteClass
      refs.tipRepoDot.className = "led " + lights.repoClass
      refs.tipChangesDot.className = "led " + lights.changesClass
      refs.tipRemoteDot.className = "led " + lights.remoteClass

      const repoText = repoTip(git)
      const changesText = changesTip(git, lights.dirty, lights.count)
      const remoteText = remoteTip(git, lights.hasRemote)
      refs.tipRepoText.textContent = repoText
      refs.tipChangesText.textContent = changesText
      refs.tipRemoteText.textContent = remoteText
      refs.ledsWrap.setAttribute("aria-label", repoText + ". " + changesText + ". " + remoteText)

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

    function openTip(pin) {
      if (pin) tipPinned = true
      tipIsOpen = true
      refs.ledTip.classList.add("is-open")
      refs.ledTip.setAttribute("aria-hidden", "false")
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
      tipIsOpen = false
      refs.ledTip.classList.remove("is-open")
      refs.ledTip.setAttribute("aria-hidden", "true")
      if (tipTimer) {
        clearTimeout(tipTimer)
        tipTimer = 0
      }
    }

    function closeTipIfUnpinned() {
      if (!tipPinned) closeTip()
    }

    function summaryRow(label, value) {
      const row = doc.createElement("div")
      row.className = "git-summary-row"
      const labelEl = doc.createElement("span")
      labelEl.className = "git-summary-label"
      labelEl.textContent = label
      const valueEl = doc.createElement("span")
      valueEl.className = "git-summary-value"
      valueEl.textContent = value
      valueEl.title = value
      row.appendChild(labelEl)
      row.appendChild(valueEl)
      refs.gitSummary.appendChild(row)
    }

    function renderGitUnavailable(message) {
      gitDetail = null
      gitAction = null
      gitBlocked = false
      refs.gitTitle.textContent = "Git unavailable"
      refs.gitSummary.textContent = ""
      summaryRow("Status", message)
      refs.gitFiles.hidden = true
      refs.gitWarnings.hidden = true
      refs.gitMessageField.hidden = true
      refs.gitNameField.hidden = true
      refs.gitVisibilityField.hidden = true
      refs.gitDescriptionField.hidden = true
      refs.gitReadmeField.hidden = true
      refs.gitPagesField.hidden = true
      refs.gitIgnoreField.hidden = true
      refs.gitNote.hidden = true
      refs.gitOutput.hidden = true
      refs.gitStatus.className = "git-status"
      refs.gitStatus.textContent = ""
      refs.gitPrimary.hidden = true
      refs.gitCancel.textContent = "Close"
      refs.gitCancel.focus()
    }

    function renderGitPanel(detail, focus, success, extra) {
      gitDetail = detail
      gitAction = decideGitAction(detail, focus)
      gitBlocked = false
      if (
        gitAction === "pages" &&
        detail.pages &&
        detail.pages.problem &&
        !detail.pages.index &&
        !detail.pages.case_mismatch
      ) {
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
      refs.gitTitle.textContent = titles[gitAction] || "Git status"

      refs.gitSummary.textContent = ""
      summaryRow("Folder", detail.root || (app && (app.path || app.dir || app.url)) || "—")
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
      refs.gitFiles.textContent = ""
      refs.gitFiles.hidden = !((gitAction === "commit" || gitAction === "init") && files.length)
      if (!refs.gitFiles.hidden) {
        files.slice(0, 12).forEach(function (item) {
          const row = doc.createElement("div")
          row.className = "git-file"
          const code = doc.createElement("span")
          code.className = "git-file-code"
          code.textContent = item.code.trim() || "?"
          const path = doc.createElement("span")
          path.className = "git-file-path"
          path.textContent = item.path
          path.title = item.path
          row.appendChild(code)
          row.appendChild(path)
          refs.gitFiles.appendChild(row)
        })
        if (files.length > 12) {
          const more = doc.createElement("div")
          more.className = "git-file-more"
          more.textContent = "+" + (files.length - 12) + " more"
          refs.gitFiles.appendChild(more)
        }
      }

      const warnings = (detail.warnings || []).filter(function (warning) {
        if (gitAction !== "init" || detail.has_gitignore) return true
        return !(
          warning.indexOf("No .gitignore") === 0 ||
          warning.indexOf("is not gitignored") >= 0
        )
      })
      refs.gitWarnings.textContent = ""
      refs.gitWarnings.hidden = warnings.length === 0
      warnings.forEach(function (warning) {
        const row = doc.createElement("div")
        row.className = "git-warning"
        row.textContent = warning
        refs.gitWarnings.appendChild(row)
      })

      const canWrite = !!gitToken
      refs.gitMessageField.hidden = !(gitAction === "commit" || gitAction === "init")
      if (!refs.gitMessageField.hidden) {
        refs.gitMessage.value = gitAction === "init"
          ? "Initial commit"
          : "Update " + ((app && app.title) || detail.branch || "app")
      }
      refs.gitNameField.hidden = gitAction !== "remote"
      if (!refs.gitNameField.hidden) refs.gitName.value = defaultRepoName(currentApp())
      refs.gitVisibilityField.hidden = gitAction !== "remote"
      if (!refs.gitVisibilityField.hidden) {
        for (let i = 0; i < refs.gitVisibilityInputs.length; i += 1) {
          refs.gitVisibilityInputs[i].checked =
            refs.gitVisibilityInputs[i].value === "private"
        }
      }
      refs.gitDescriptionField.hidden = gitAction !== "remote"
      if (!refs.gitDescriptionField.hidden) refs.gitDescription.value = ""
      const readmeMissing = !(detail.readme && detail.readme.exists)
      refs.gitReadmeField.hidden = !(
        (gitAction === "remote" || gitAction === "pages") && readmeMissing
      )
      if (!refs.gitReadmeField.hidden) {
        refs.gitReadme.value = "# " + ((app && app.title) || "App") + "\n\n"
      }
      refs.gitPagesField.hidden = gitAction !== "remote"
      if (!refs.gitPagesField.hidden) refs.gitPages.checked = false
      refs.gitIgnoreField.hidden = gitAction !== "init" || !!detail.has_gitignore
      if (!refs.gitIgnoreField.hidden) refs.gitIgnore.checked = true

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
        if (detail.pages && detail.pages.problem) {
          notes.push(detail.pages.problem)
        } else {
          notes.push("This enables GitHub Pages for the current branch and sets the Pages address as the repo homepage.")
        }
      }
      if (detail.state === "detached") notes.push("You are on a detached HEAD. Switch to a branch first.")
      if (detail.state === "conflicted") notes.push("Resolve the merge conflicts, then try again.")
      if (detail.state === "diverged") notes.push("Local and remote have diverged. Pull or rebase before pushing.")
      if (detail.state === "behind" && gitAction === "info") {
        notes.push("The remote has commits you do not have yet.")
      }
      if (gitAction === "info" && !notes.length) notes.push("Everything is in order.")
      refs.gitNote.textContent = notes.join("\n\n")
      refs.gitNote.hidden = notes.length === 0

      refs.gitOutput.hidden = true
      refs.gitOutput.textContent = ""
      refs.gitStatus.className = "git-status" + (success ? " is-good" : "")
      refs.gitStatus.textContent = success || ""

      gitBlocked =
        !canWrite ||
        detail.identity_ok === false && (gitAction === "commit" || gitAction === "init") ||
        (gitAction === "remote" || gitAction === "pages") && detail.gh === false ||
        gitAction === "pages" && !!(detail.pages && detail.pages.problem) ||
        gitAction === "pages-entry" && !(detail.pages && detail.pages.entry)
      refs.gitPrimary.textContent = labels[gitAction] || ""
      refs.gitPrimary.hidden = !labels[gitAction]
      refs.gitPrimary.disabled = gitBlocked
      refs.gitCancel.textContent = gitAction === "info" ? "Close" : "Cancel"
      refs.gitCancel.disabled = false
      refs.gitClose.disabled = false

      if (!refs.gitReadmeField.hidden) refs.gitReadme.focus()
      else if (gitAction === "commit" || gitAction === "init") refs.gitMessage.focus()
      else if (gitAction === "remote") refs.gitName.focus()
      else if (gitAction === "push" || gitAction === "pages" || gitAction === "pages-entry") refs.gitPrimary.focus()
      else refs.gitCancel.focus()
    }

    function openGitPanel(focus) {
      const app = currentApp()
      if (!app || !refs.gitOverlay.hidden) return
      closeMenu(false)
      closeTip()
      gitReturnFocus = root.activeElement || doc.activeElement
      refs.gitOverlay.hidden = false
      gitBusy = false
      refs.gitStatus.className = "git-status"
      refs.gitStatus.textContent = ""
      refs.gitOutput.hidden = true
      refs.gitOutput.textContent = ""
      refs.gitTitle.textContent = "Checking Git…"
      refs.gitSummary.textContent = ""
      refs.gitFiles.hidden = true
      refs.gitWarnings.hidden = true
      refs.gitNote.hidden = true
      refs.gitMessageField.hidden = true
      refs.gitNameField.hidden = true
      refs.gitVisibilityField.hidden = true
      refs.gitDescriptionField.hidden = true
      refs.gitReadmeField.hidden = true
      refs.gitPagesField.hidden = true
      refs.gitIgnoreField.hidden = true
      refs.gitPrimary.hidden = true

      if (location.protocol !== "http:" && location.protocol !== "https:") {
        renderGitUnavailable("Start the ribbon server to use Git actions.")
        return
      }

      const token = typeof options.getToken === "function"
        ? Promise.resolve(options.getToken())
        : Promise.resolve("")
      token
        .then(function (value) {
          gitToken = value || ""
          if (refs.gitOverlay.hidden) return null
          const dir = app.path || app.dir || app.url || ""
          return fetch("/__ribbon/git.json?dir=" + encodeURIComponent(dir), { cache: "no-store" })
            .then(function (response) {
              if (!response.ok) throw new Error("HTTP " + response.status)
              return response.json()
            })
            .then(function (detail) {
              if (refs.gitOverlay.hidden) return
              setGit(detail)
              if (app === currentApp()) app.git = detail
              renderGitPanel(detail, focus, "")
            })
        })
        .catch(function (error) {
          if (refs.gitOverlay.hidden) return
          renderGitUnavailable("Could not read Git status: " + (error.message || error))
        })
    }

    function closeGitPanel() {
      if (gitBusy) return
      refs.gitOverlay.hidden = true
      gitDetail = null
      gitAction = null
      if (gitReturnFocus && gitReturnFocus.focus) {
        try {
          gitReturnFocus.focus()
        } catch (_) { /* target may be gone */ }
      }
      gitReturnFocus = null
    }

    function setGitBusy(busy) {
      gitBusy = busy
      refs.gitPrimary.disabled = busy || gitBlocked
      refs.gitCancel.disabled = busy
      refs.gitClose.disabled = busy
      if (busy) {
        refs.gitPrimary.textContent = "Working…"
      } else if (gitAction) {
        const labels = {
          init: "Create repo + commit",
          commit: "Commit changes",
          push: "Push commits",
          remote: "Create repo + push",
          pages: "Publish to GitHub Pages",
          "pages-entry": "Create index.html"
        }
        refs.gitPrimary.textContent = labels[gitAction] || "Continue"
      }
    }

    function showGitError(data) {
      const error = (data && (data.error || data.message)) || "The Git action failed."
      const output = (data && data.output) || ""
      refs.gitStatus.className = "git-status is-bad"
      refs.gitStatus.textContent = error.split("\n")[0].slice(0, 140)
      refs.gitOutput.textContent = [ error, output ].filter(Boolean).join("\n\n")
      refs.gitOutput.hidden = !refs.gitOutput.textContent
    }

    function submitGitAction() {
      if (gitBusy || !gitAction) return
      const app = currentApp()
      if (!app) return

      const payload = { action: gitAction, dir: app.path || app.dir || app.url || "" }
      if (gitAction === "init" || gitAction === "commit") {
        payload.message = refs.gitMessage.value.trim()
        if (!payload.message) {
          refs.gitMessage.focus()
          return
        }
      }
      if (gitAction === "init") payload.gitignore = refs.gitIgnore.checked
      if (gitAction === "remote") {
        payload.name = refs.gitName.value.trim()
        if (!payload.name) {
          refs.gitName.focus()
          return
        }
        const checked = root.querySelector('input[name="git-visibility"]:checked')
        payload.visibility = checked ? checked.value : "private"
        payload.description = refs.gitDescription.value.trim()
        payload.pages = refs.gitPages.checked
      }
      if (!refs.gitReadmeField.hidden) payload.readme = refs.gitReadme.value

      setGitBusy(true)
      refs.gitStatus.className = "git-status"
      refs.gitStatus.textContent = "Working…"
      refs.gitOutput.hidden = true
      refs.gitOutput.textContent = ""

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
            if (app === currentApp()) app.git = data.status
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

    refs.ledsWrap.addEventListener("click", function (event) {
      const button = event.target && event.target.closest
        ? event.target.closest(".led-btn")
        : null
      if (!button) return
      event.stopPropagation()
      openGitPanel(button.getAttribute("data-led"))
    })
    refs.ledsWrap.addEventListener("pointerenter", function () {
      if (hoverCapable) openTip(false)
    })
    refs.ledsWrap.addEventListener("pointerleave", closeTipIfUnpinned)
    const ledButtons = refs.ledButtons || []
    for (let i = 0; i < ledButtons.length; i += 1) {
      ledButtons[i].addEventListener("focus", function () {
        openTip(false)
      })
      ledButtons[i].addEventListener("blur", closeTipIfUnpinned)
    }
    doc.addEventListener("pointerdown", function (event) {
      if (!tipIsOpen) return
      const path = event.composedPath ? event.composedPath() : []
      if (path.indexOf(refs.ledsWrap.parentNode) !== -1) return
      closeTip()
    }, true)

    if (refs.gitCancel) refs.gitCancel.addEventListener("click", closeGitPanel)
    if (refs.gitClose) refs.gitClose.addEventListener("click", closeGitPanel)
    if (refs.gitPrimary) refs.gitPrimary.addEventListener("click", submitGitAction)
    if (refs.gitOverlay) {
      refs.gitOverlay.addEventListener("pointerdown", function (event) {
        if (event.target === refs.gitOverlay) closeGitPanel()
      })
      refs.gitOverlay.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return
        event.preventDefault()
        closeGitPanel()
      })
    }

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

    return {
      setApps: function (next) {
        apps = Array.isArray(next) ? next : []
        if (menuOpen) renderMenu()
      },
      setStale: function (next) {
        stale = !!next
        if (menuOpen) renderMenu()
      },
      setIndex: function (next) {
        index = typeof next === "number" ? next : -1
      },
      setCanDelete: function (next) {
        canDelete = !!next
      },
      setChannel: setChannel,
      currentApp: currentApp,
      appKey: appKey,
      isFavorite: isFavorite,
      updateCurrentStar: updateCurrentStar,
      updateCurrentMeta: updateCurrentMeta,
      renderMenu: renderMenu,
      openMenu: openMenu,
      closeMenu: closeMenu,
      removeFavorite: removeFavorite,
      isMenuOpen: function () { return menuOpen },
      setGit: setGit,
      closeTip: closeTip,
      isTipOpen: function () { return tipIsOpen },
      closeGitPanel: closeGitPanel
    }
  }

  window.__RIBBON_BAR__ = {
    appKey: appKey,
    neighborUrls: neighborUrls,
    pad: pad,
    matchesQuery: matchesQuery,
    defaultRepoName: defaultRepoName,
    gitLights: gitLights,
    gitWorkRank: gitWorkRank,
    decideGitAction: decideGitAction,
    repoTip: repoTip,
    changesTip: changesTip,
    remoteTip: remoteTip,
    createBar: createBar
  }
})()

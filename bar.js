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
    isParked: isParked
  }
})()

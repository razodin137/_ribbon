(function () {
  "use strict"

  function esc(value) {
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

  function folderLabel(path) {
    if (!path || path === ".") return "/"
    return "/" + path
  }

  function dateLabel(mtime) {
    if (!mtime) return "—"
    try {
      return new Intl.DateTimeFormat("en", {
        month: "short",
        day: "numeric",
        year: "numeric"
      }).format(new Date(mtime * 1000))
    } catch (error) {
      return "—"
    }
  }

  const TYPE_COLORS = [
    "oklch(68% 0.11 78)",
    "oklch(64% 0.09 145)",
    "oklch(62% 0.09 245)",
    "oklch(64% 0.11 28)",
    "oklch(64% 0.08 305)",
    "oklch(64% 0.07 195)"
  ]

  function typeColor(index) {
    return TYPE_COLORS[index % TYPE_COLORS.length]
  }

  function formatSize(bytes) {
    if (!bytes) return "0 B"
    const units = [ "B", "KB", "MB", "GB" ]
    let value = bytes
    let unit = 0
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024
      unit += 1
    }
    const rounded = unit === 0 || value >= 10 ? Math.round(value) : value.toFixed(1)
    return rounded + " " + units[unit]
  }

  function fileList(files) {
    if (!files || !files.length) {
      return '<p class="rc-empty">No files listed.</p>'
    }
    return "<ul class=\"rc-files-list\">" + files.map(function (name) {
      const folder = name.charAt(name.length - 1) === "/"
      return "<li class=\"rc-file" + (folder ? " is-folder" : "") + "\">" +
        esc(name) + "</li>"
    }).join("") + "</ul>"
  }

  function statsLine(stats) {
    if (!stats) return ""
    if (!stats.files && !stats.folders) {
      return '<span class="rc-stats">Empty folder</span>'
    }
    const bits = []
    bits.push(stats.files + (stats.files === 1 ? " file" : " files"))
    bits.push(stats.folders + (stats.folders === 1 ? " folder" : " folders"))
    if (stats.size) bits.push(formatSize(stats.size))
    return '<span class="rc-stats">' + bits.map(function (bit) {
      return "<span>" + esc(bit) + "</span>"
    }).join('<span class="rc-dot">·</span>') + "</span>"
  }

  function typeBar(stats) {
    if (!stats || !stats.types || !stats.types.length) return ""
    const total = stats.types.reduce(function (sum, item) {
      return sum + item.count
    }, 0)
    if (!total) return ""
    return '<div class="rc-bar" role="img" aria-label="File types">' +
      stats.types.map(function (item, index) {
        const width = Math.max(3, (item.count / total) * 100)
        return '<span class="rc-bar-seg" style="width:' + width.toFixed(2) +
          "%;background:" + typeColor(index) + '" title="' + esc(item.ext) +
          " · " + item.count + '"></span>'
      }).join("") +
      "</div>" +
      '<div class="rc-types">' +
      stats.types.map(function (item, index) {
        return '<span class="rc-type-chip"><i style="background:' +
          typeColor(index) + '"></i>' + esc(item.ext) + " <b>" +
          item.count + "</b></span>"
      }).join("") +
      "</div>"
  }

  function tileGrid(stats, files) {
    if (!stats || !stats.recent || !stats.recent.length) return fileList(files)
    return '<div class="rc-grid">' + stats.recent.map(function (item) {
      const ext = item.dir
        ? "DIR"
        : (item.name.split(".").pop() || "FILE").slice(0, 4).toUpperCase()
      return '<div class="rc-tile' + (item.dir ? " is-folder" : "") + '">' +
        '<span class="rc-tile-badge">' + esc(ext) + "</span>" +
        '<span class="rc-tile-name" title="' + esc(item.name) + '">' +
        esc(item.name) + (item.dir ? "/" : "") + "</span>" +
        '<span class="rc-tile-size">' +
        (item.dir ? "folder" : formatSize(item.size)) + "</span>" +
        "</div>"
    }).join("") + "</div>"
  }

  function typeLabel(app) {
    if (app.kind === "markdown") return "Markdown document"
    const type = app.type || "Project"
    return type === "Project" ? "Local project" : type + " project"
  }

  function headHtml(app) {
    return '<header class="rc-head">' +
      '<span class="rc-stamp" aria-hidden="true">' + esc(app.icon || "PR") + "</span>" +
      '<div class="rc-titles">' +
        '<p class="rc-type">' + esc(typeLabel(app)) + "</p>" +
        '<h1 class="rc-title">' + esc(app.title || "Untitled") + "</h1>" +
      "</div>" +
    "</header>"
  }

  function hiddenRow(entry) {
    const classes = [ "rc-tree-row" ]
    if (entry.dir) classes.push("is-dir")
    if (entry.ignored) classes.push("is-ignored")
    if (entry.link) classes.push("is-link")

    const tags = [ ]
    if (entry.ignored) tags.push('<span class="rc-tag is-ignored">ignored</span>')
    if (entry.secret && !entry.ignored) {
      tags.push('<span class="rc-tag is-alert">not ignored</span>')
    }
    if (entry.name === ".git") tags.push('<span class="rc-tag is-special">git</span>')

    const size = entry.dir || entry.link
      ? ""
      : '<span class="rc-tree-size">' + esc(formatSize(entry.size)) + "</span>"

    const depth = Math.max(0, Math.floor(Number(entry.depth) || 0))

    return '<li class="' + classes.join(" ") + '" style="--depth: ' + depth + '">' +
      '<span class="rc-tree-name">' + esc(entry.path) +
        (entry.dir ? "/" : "") + (entry.link ? " →" : "") + "</span>" +
      '<span class="rc-tree-tags">' + tags.join("") + "</span>" +
      size +
    "</li>"
  }

  function hiddenSummary(tree) {
    if (!tree || !tree.entries) return '<span class="rc-stats">not available</span>'
    const hidden = tree.entries.filter(function (entry) {
      return entry.hidden
    })
    const ignored = hidden.filter(function (entry) {
      return entry.ignored
    }).length
    const bits = [
      hidden.length + (hidden.length === 1 ? " entry" : " entries"),
      ignored + " ignored"
    ]
    return '<span class="rc-stats">' + bits.map(function (bit) {
      return "<span>" + esc(bit) + "</span>"
    }).join('<span class="rc-dot">·</span>') + "</span>"
  }

  function hiddenSection(tree) {
    let body
    if (!tree || !tree.entries) {
      body = '<p class="rc-note">This snapshot cannot see hidden files or ' +
        "ignore rules. Start <code>ribbon.py</code> for the full overview.</p>"
    } else {
      const hidden = tree.entries.filter(function (entry) {
        return entry.hidden
      }).sort(function (a, b) {
        if (a.name === ".git") return 1
        if (b.name === ".git") return -1
        return 0
      })
      body = hidden.length
        ? '<ul class="rc-tree">' + hidden.map(hiddenRow).join("") + "</ul>"
        : '<p class="rc-empty">No hidden files.</p>'
    }

    return '<section class="rc-hidden">' +
      '<div class="rc-contents-head">' +
        '<span class="rc-contents-title">Hidden</span>' +
        hiddenSummary(tree) +
      "</div>" +
      body +
    "</section>"
  }

  function sensitiveHtml(tree) {
    if (!tree || !tree.sensitive || !tree.sensitive.length) return ""
    const names = tree.sensitive.map(function (name) {
      return esc(name)
    }).join(", ")
    return '<p class="rc-warn">Not ignored: ' + names +
      ". Add it to <code>.gitignore</code> before you commit.</p>"
  }

  function ignoreHtml(tree) {
    if (!tree) return ""
    if (!tree.gitignore_present) {
      return '<section class="rc-ignore">' +
        '<div class="rc-contents-head">' +
          '<span class="rc-contents-title">.gitignore</span>' +
        "</div>" +
        '<p class="rc-empty">No .gitignore in this folder. Generated files ' +
        "may be staged by mistake.</p>" +
      "</section>"
    }
    if (!tree.gitignore.trim()) {
      return '<section class="rc-ignore">' +
        '<div class="rc-contents-head">' +
          '<span class="rc-contents-title">' +
            esc(tree.gitignore_label || ".gitignore") + "</span>" +
          '<span class="rc-stats"><span>empty</span></span>' +
        "</div>" +
        '<p class="rc-empty">This .gitignore has no rules yet.</p>' +
      "</section>"
    }
    const rules = tree.gitignore.split("\n").filter(function (line) {
      const trimmed = line.trim()
      return trimmed && trimmed.charAt(0) !== "#"
    }).length
    return '<section class="rc-ignore">' +
      '<div class="rc-contents-head">' +
        '<span class="rc-contents-title">' +
          esc(tree.gitignore_label || ".gitignore") + "</span>" +
        '<span class="rc-stats"><span>' + rules +
          (rules === 1 ? " rule" : " rules") + "</span></span>" +
      "</div>" +
      '<pre class="rc-ignore-pre">' + esc(tree.gitignore) + "</pre>" +
    "</section>"
  }

  function overviewHtml(app) {
    const description = app.description || (
      app.kind === "page"
        ? "No description yet. Add a meta description or README to this folder."
        : "A folder in your ribbon, shown here because it has no web page."
    )
    const stats = app.stats
    const tree = app.tree || null
    const run = app.run
      ? '<div class="rc-fact">' +
          "<dt>Run</dt>" +
          '<dd><code class="rc-run">' + esc(app.run) + "</code></dd>" +
        "</div>"
      : ""
    const footer = app.kind === "page"
      ? "The folder behind this page."
      : "No web page in this folder, so Ribbon shows its contents."

    return '<article class="rc-card" style="--rc-accent: ' +
      esc(app.color || "#d0a64a") + '">' +
      headHtml(app) +
      '<p class="rc-desc">' + esc(description) + "</p>" +
      '<dl class="rc-facts">' +
        '<div class="rc-fact">' +
          "<dt>Folder</dt><dd>" + esc(folderLabel(app.path || app.dir)) + "</dd>" +
        "</div>" +
        '<div class="rc-fact">' +
          "<dt>Updated</dt><dd>" + esc(dateLabel(app.mtime)) + "</dd>" +
        "</div>" +
        run +
      "</dl>" +
      '<section class="rc-contents">' +
        '<div class="rc-contents-head">' +
          '<span class="rc-contents-title">Contents</span>' +
          statsLine(stats) +
        "</div>" +
        typeBar(stats) +
        tileGrid(stats, app.files) +
      "</section>" +
      hiddenSection(tree) +
      sensitiveHtml(tree) +
      ignoreHtml(tree) +
      '<footer class="rc-foot">' + esc(footer) + "</footer>" +
    "</article>"
  }

  function mount() {
    const node = document.getElementById("ribbon-card")
    if (!node || !window.__RIBBON_CARD_APP__) return
    node.innerHTML = overviewHtml(window.__RIBBON_CARD_APP__)
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount)
  } else {
    mount()
  }
})()

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

  function cardHtml(app) {
    const type = app.type || "Project"
    const icon = app.icon || "PR"
    const color = app.color || "#d0a64a"
    const description = app.description ||
      "A local project in your ribbon. Open the folder to see what it does."
    const run = app.run
      ? '<section class="rc-block">' +
          '<h2 class="rc-label">Run</h2>' +
          '<code class="rc-run">' + esc(app.run) + "</code>" +
        "</section>"
      : ""

    return '<article class="rc-card" style="--rc-accent: ' + esc(color) + '">' +
      '<div class="rc-glow" aria-hidden="true"></div>' +
      '<header class="rc-head">' +
        '<span class="rc-glyph" aria-hidden="true">' + esc(icon) + "</span>" +
        '<div class="rc-titles">' +
          '<p class="rc-kicker">' + esc(type) + " project</p>" +
          '<h1 class="rc-title">' + esc(app.title || "Untitled") + "</h1>" +
        "</div>" +
      "</header>" +
      '<p class="rc-desc">' + esc(description) + "</p>" +
      '<dl class="rc-meta">' +
        "<div><dt>Folder</dt><dd>" +
          esc(folderLabel(app.path || app.dir)) + "</dd></div>" +
        "<div><dt>Updated</dt><dd>" + esc(dateLabel(app.mtime)) + "</dd></div>" +
      "</dl>" +
      run +
      '<section class="rc-block">' +
        '<h2 class="rc-label">Files</h2>' +
        fileList(app.files) +
      "</section>" +
      '<footer class="rc-foot">Ribbon · project card</footer>' +
    "</article>"
  }

  function mount() {
    const node = document.getElementById("ribbon-card")
    if (!node || !window.__RIBBON_CARD_APP__) return
    node.innerHTML = cardHtml(window.__RIBBON_CARD_APP__)
  }

  window.__RIBBON_CARD_HTML__ = cardHtml

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount)
  } else {
    mount()
  }
})()

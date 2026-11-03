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

  function typeLabel(app) {
    if (app.kind === "markdown") return "Markdown document"
    const type = app.type || "Project"
    return type === "Project" ? "Local project" : type + " project"
  }

  function cardHtml(app) {
    const icon = app.icon || "PR"
    const color = app.color || "#d0a64a"
    const description = app.description ||
      "A local project in your ribbon, shown here because the folder has no web page."
    const run = app.run
      ? '<div class="rc-fact">' +
          "<dt>Run</dt>" +
          '<dd><code class="rc-run">' + esc(app.run) + "</code></dd>" +
        "</div>"
      : ""

    return '<article class="rc-card" style="--rc-accent: ' + esc(color) + '">' +
      '<header class="rc-head">' +
        '<span class="rc-stamp" aria-hidden="true">' + esc(icon) + "</span>" +
        '<div class="rc-titles">' +
          '<p class="rc-type">' + esc(typeLabel(app)) + "</p>" +
          '<h1 class="rc-title">' + esc(app.title || "Untitled") + "</h1>" +
        "</div>" +
      "</header>" +
      '<p class="rc-desc">' + esc(description) + "</p>" +
      '<dl class="rc-facts">' +
        '<div class="rc-fact">' +
          "<dt>Folder</dt><dd>" + esc(folderLabel(app.path || app.dir)) + "</dd>" +
        "</div>" +
        '<div class="rc-fact">' +
          "<dt>Updated</dt><dd>" + esc(dateLabel(app.mtime)) + "</dd>" +
        "</div>" +
        run +
        '<div class="rc-fact">' +
          "<dt>Files</dt><dd>" + fileList(app.files) + "</dd>" +
        "</div>" +
      "</dl>" +
      '<footer class="rc-foot">' +
        "No web page in this folder, so Ribbon shows its project card." +
      "</footer>" +
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

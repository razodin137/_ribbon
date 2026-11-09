"""The page shell Ribbon injects before any page script runs.

The boot script, the bar host style and markup, and the page offset all
travel together: every served page receives them, and none depends on the
request.
"""

from __future__ import annotations

from config import BAR_HEIGHT


# Runs right after the declarative shadow bar parses. data-ribbon-booting turns
# off the bar's transition, so the hidden state lands without animating. Two
# frames later the attribute is removed and normal transitions resume.
# ribbon.js reads the same two keys and takes over.
BOOT_SCRIPT = (
    b"<script>try{"
    b'var h=document.querySelector("[data-ribbon-host]");'
    b"if(h){"
    b'h.setAttribute("data-ribbon-booting","");'
    b"requestAnimationFrame(function(){requestAnimationFrame(function(){"
    b'h.removeAttribute("data-ribbon-booting")'
    b"})});"
    b'if(sessionStorage.getItem("ribbon:hidden")==="1")'
    b'h.setAttribute("data-ribbon-hidden","");'
    b'else if(sessionStorage.getItem("ribbon:scroll")===location.href)'
    b'h.setAttribute("data-ribbon-scrolled","")'
    b"}}catch(_){}"
    b"</script>"
)


# The bar floats above the page, so the document needs a strip of its own to
# sit under it. A generated block on the root element holds that strip in
# normal flow, so it exists at first paint even when the scripts are slow or
# blocked. It is not a child of <body>: a body child takes part in the page's
# layout, so it would sit beside the content in a row-flex body or become an
# extra grid item. ribbon.js removes the strip with the same host attribute it
# uses when the bar is hidden by hand.
PAGE_OFFSET_CSS = (
    f'html::before{{content:"";display:block;height:{BAR_HEIGHT}px;pointer-events:none;}}\n'
    "html:has([data-ribbon-host][data-ribbon-hidden])::before{display:none;}\n"
)

BAR_HOST_STYLE = (
    "position:fixed!important;"
    "top:0!important;"
    "right:0!important;"
    "left:0!important;"
    "width:100%!important;"
    "height:auto!important;"
    "margin:0!important;"
    "padding:0!important;"
    "border:0!important;"
    "background:transparent!important;"
    "z-index:2147483647!important;"
    "display:block!important;"
    "pointer-events:none!important;"
    "isolation:isolate!important;"
    "view-transition-name:ribbon-bar!important"
)

# Cross-document view transitions: the bar is a named element in both
# documents, so it is lifted out of the root cross-fade and survives the
# navigation unchanged. Naming the host (not .bar inside its shadow root)
# is what makes the snapshot part of the document's view transition tree.
# Reduced motion opts out of the transition entirely; the blanket rule is
# there for engines that ignore @view-transition inside @media.
VIEW_TRANSITION_CSS = (
    "@view-transition { navigation: auto; }\n"
    "::view-transition-old(ribbon-bar),\n"
    "::view-transition-new(ribbon-bar) {\n"
    "  animation: none;\n"
    "  mix-blend-mode: normal;\n"
    "}\n"
    "@media (prefers-reduced-motion: reduce) {\n"
    "  @view-transition { navigation: none; }\n"
    "  ::view-transition-old(root),\n"
    "  ::view-transition-new(root) {\n"
    "    animation: none;\n"
    "  }\n"
    "}\n"
)

BAR_MARKUP = "".join(
    line.strip()
    for line in """\
<div class="bar" role="navigation" aria-label="App ribbon">
  <div class="meta">
    <span class="led-wrap">
      <span class="leds" role="group" aria-label="Git status" aria-describedby="led-tip">
        <button class="led-btn" type="button" data-led="repo" aria-label="Repository status"><span class="led off" data-led-dot="repo" aria-hidden="true"></span></button>
        <button class="led-btn" type="button" data-led="changes" aria-label="Changes status"><span class="led off" data-led-dot="changes" aria-hidden="true"></span></button>
        <button class="led-btn" type="button" data-led="remote" aria-label="Remote status"><span class="led off" data-led-dot="remote" aria-hidden="true"></span></button>
      </span>
      <span class="led-tip" id="led-tip" role="tooltip" aria-hidden="true">
        <span class="led-tip-row"><span class="led off" data-tip-led="repo" aria-hidden="true"></span><span data-tip-text="repo"></span></span>
        <span class="led-tip-row"><span class="led off" data-tip-led="changes" aria-hidden="true"></span><span data-tip-text="changes"></span></span>
        <span class="led-tip-row"><span class="led off" data-tip-led="remote" aria-hidden="true"></span><span data-tip-text="remote"></span></span>
        <span class="led-tip-hint">Tap again for Git actions</span>
      </span>
    </span>
    <span class="count"></span>
  </div>
  <div class="title-wrap">
    <button class="star-btn title-star" type="button" aria-pressed="false" aria-label="Add to favorites" title="Add to favorites">☆</button>
    <span class="home-wrap" data-home hidden>
      <a class="title-home" data-home-link href="#" aria-label="Ribbon home" title="Back to Ribbon grid">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 10.5L12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-6h6v6"/></svg>
      </a>
    </span>
    <button class="title" type="button" aria-haspopup="dialog" aria-expanded="false" title="Show all apps">
      <span class="title-text"></span>
      <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
    </button>
  </div>
  <div class="actions">
    <button class="btn" type="button" data-act="prev" aria-label="Previous app" title="Previous app — [">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>
      <span class="label">Back</span>
    </button>
    <button class="btn" type="button" data-act="next" aria-label="Next app" title="Next app — ]">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
      <span class="label">Next</span>
    </button>
    <button class="btn" type="button" data-act="contents" aria-label="Show contents" aria-pressed="false" title="Show contents — C">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
      <span class="label">Contents</span>
    </button>
    <button class="btn" type="button" data-act="drift" aria-label="Drift to another app" title="Drift to another app — R">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 4l3 3-3 3"/><path d="M18 20l3-3-3-3"/><path d="M3 7h3c2 0 3.5 1 4.5 2.5l3 5C14.5 16 16 17 18 17h3"/><path d="M3 17h3c2 0 3.5-1 4.5-2.5l3-5C14.5 8 16 7 18 7h3"/></svg>
      <span class="label">Drift</span>
    </button>
    <button class="btn" type="button" data-act="reload" aria-label="Reload app" title="Reload app — Shift+R">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>
    </button>
    <span class="sep" aria-hidden="true"></span>
    <button class="btn" type="button" data-act="hide" aria-label="Hide ribbon" title="Hide ribbon — H">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6L6 18"/><path d="M6 6l12 12"/></svg>
    </button>
  </div>
  <div class="menu" hidden role="dialog" aria-label="All apps">
    <div class="menu-top">
      <div class="menu-current">
        <span class="menu-current-label">Current app</span>
        <span class="menu-current-title"></span>
        <span class="menu-current-meta"></span>
      </div>
      <button class="star-btn" type="button" aria-pressed="false" aria-label="Add to favorites" title="Add to favorites">☆</button>
    </div>
    <div class="menu-current-hint">drift deals from the active channel</div>
    <div class="menu-channels" role="group" aria-label="Channels"></div>
    <div class="menu-search">
      <input class="menu-input" type="search" placeholder="Search apps…" aria-label="Search apps" autocomplete="off" spellcheck="false">
    </div>
    <div class="menu-scroll">
      <div class="menu-section" data-section="favorites" hidden>
        <div class="menu-heading">Favorites</div>
        <div class="menu-list" data-list="favorites"></div>
      </div>
      <div class="menu-section" data-section="all">
        <div class="menu-heading">All apps</div>
        <div class="menu-list" data-list="all"></div>
      </div>
      <div class="menu-empty" hidden>No apps match.</div>
    </div>
  </div>
</div>
<div class="card-overlay" hidden>
  <button class="card-close" type="button" aria-label="Close contents" title="Close contents — Esc">✕ Close</button>
  <iframe class="card-frame" title="Project contents"></iframe>
</div>
<button class="peek" type="button" aria-label="Show ribbon" title="Show ribbon — H">
  <span aria-hidden="true">▤</span><span class="peek-label">ribbon</span>
</button>
<div class="git-overlay" hidden>
  <div class="git-dialog" role="dialog" aria-modal="true" aria-labelledby="git-title">
    <div class="git-head">
      <div class="git-heading">
        <div class="git-kicker">Git</div>
        <div class="git-title" id="git-title"></div>
      </div>
      <button class="git-close" type="button" aria-label="Close">✕</button>
    </div>
    <div class="git-body">
      <div class="git-summary"></div>
      <div class="git-files" hidden></div>
      <div class="git-warnings" hidden></div>
      <label class="git-field git-message-field" hidden>
        <span class="git-label">Commit message</span>
        <input class="git-input git-message" type="text" maxlength="2000" autocomplete="off">
      </label>
      <label class="git-field git-name-field" hidden>
        <span class="git-label">GitHub repo name</span>
        <input class="git-input git-name" type="text" maxlength="100" autocomplete="off" spellcheck="false">
      </label>
      <div class="git-field git-visibility-field" hidden>
        <span class="git-label">Visibility</span>
        <div class="git-radios">
          <label class="git-radio"><input type="radio" name="git-visibility" value="private" checked> Private</label>
          <label class="git-radio"><input type="radio" name="git-visibility" value="public"> Public</label>
        </div>
      </div>
      <label class="git-field git-description-field" hidden>
        <span class="git-label">Description (optional)</span>
        <input class="git-input git-description" type="text" maxlength="350" autocomplete="off" placeholder="What is this app?">
      </label>
      <label class="git-field git-readme-field" hidden>
        <span class="git-label">README.md</span>
        <textarea class="git-input git-textarea git-readme" rows="6" maxlength="20000" spellcheck="false" placeholder="Write a short README…"></textarea>
        <span class="git-hint">No README yet. Ribbon will write this to README.md, commit it, and push it before publishing.</span>
      </label>
      <label class="git-check git-pages-field" hidden>
        <input type="checkbox" class="git-pages">
        <span>Publish with GitHub Pages and set it as the repo homepage</span>
      </label>
      <label class="git-check git-ignore-field" hidden>
        <input type="checkbox" class="git-ignore" checked>
        <span>Add a .gitignore for node_modules, .venv, dist…</span>
      </label>
      <div class="git-note" hidden></div>
      <pre class="git-output" hidden></pre>
    </div>
    <div class="git-actions">
      <span class="git-status"></span>
      <button class="btn git-cancel" type="button">Close</button>
      <button class="btn git-primary" type="button" hidden></button>
    </div>
  </div>
</div>
<div class="delete-overlay" hidden>
  <div class="delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-warning">
    <div class="delete-head">
      <div class="delete-heading">
        <div class="delete-kicker">Delete folder</div>
        <div class="delete-title" id="delete-title"></div>
      </div>
      <button class="git-close delete-close" type="button" aria-label="Close">✕</button>
    </div>
    <div class="delete-body">
      <p class="delete-warn" id="delete-warning">This removes the folder and everything inside it. It cannot be undone.</p>
      <div class="delete-path"></div>
      <div>
        <div class="delete-command-label">Command</div>
        <pre class="delete-command"></pre>
      </div>
      <div class="delete-note">Ribbon will run exactly this command, then remove the folder from the list.</div>
      <pre class="delete-command delete-output" hidden></pre>
    </div>
    <div class="delete-actions">
      <span class="delete-status" role="status" aria-live="polite"></span>
      <button class="btn delete-cancel" type="button">Cancel</button>
      <button class="btn delete-primary" type="button" disabled>Delete folder</button>
    </div>
  </div>
</div>
""".splitlines()
)

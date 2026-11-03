/* Ribbon — a floating, auto-hiding switcher for a folder of HTML apps.
 *
 * Normally injected by ribbon.py. It can also be included by hand:
 *   <script src="/__ribbon/ribbon.js" defer></script>
 * or, with no server, provide the list yourself before the script runs:
 *   window.__RIBBON_APPS__ = [{ url: "/app/", title: "App" }];
 */
(function () {
  "use strict";

  if (window.__RIBBON_MOUNTED__) return;
  if (window.self !== window.top) return;
  window.__RIBBON_MOUNTED__ = true;

  var scriptEl = document.currentScript || document.querySelector("script[data-ribbon]");
  var scriptBase = "/__ribbon/";
  if (scriptEl && scriptEl.src) {
    try {
      scriptBase = new URL(".", scriptEl.src).href;
    } catch (_) {}
  }

  var STORAGE_KEY = "ribbon:hidden";
  var CSS = `
    :host { all: initial; }
    *, *::before, *::after { box-sizing: border-box; }

    .bar {
      position: relative;
      display: flex;
      align-items: center;
      gap: 12px;
      height: 40px;
      margin: 0;
      padding: 0 7px 0 13px;
      background: rgba(17, 18, 15, 0.9);
      color: #eee9dc;
      border-bottom: 1px solid rgba(255, 255, 255, 0.13);
      box-shadow: 0 1px 0 rgba(0, 0, 0, 0.35), 0 8px 24px rgba(0, 0, 0, 0.18);
      -webkit-backdrop-filter: blur(18px) saturate(1.15);
      backdrop-filter: blur(18px) saturate(1.15);
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 13px;
      line-height: 1;
      -webkit-font-smoothing: antialiased;
      user-select: none;
      -webkit-user-select: none;
      pointer-events: auto;
      transform: translateY(0);
      transition: transform 260ms cubic-bezier(.2, .7, .2, 1), opacity 180ms ease;
      will-change: transform;
    }
    .bar.is-gone {
      transform: translateY(calc(-100% - 2px));
      opacity: 0;
      pointer-events: none;
    }

    .meta {
      display: flex;
      align-items: center;
      gap: 9px;
      flex: 0 0 auto;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 10px;
      letter-spacing: .12em;
      color: #979284;
    }
    .led-wrap { position: relative; display: flex; align-items: center; flex: none; }
    .leds {
      appearance: none;
      -webkit-appearance: none;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      height: 28px;
      margin: 0 0 0 -7px;
      padding: 0 7px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      cursor: pointer;
      font: inherit;
      touch-action: manipulation;
    }
    .leds:hover { background: rgba(255, 255, 255, .06); }
    .leds:focus-visible { outline: 2px solid #d0a64a; outline-offset: 1px; }
    .led {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #454741;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .06);
      transition: background .2s ease, box-shadow .2s ease;
      flex: none;
    }
    .led.ok {
      background: #65d18a;
      box-shadow: 0 0 0 3px rgba(101, 209, 138, .1), 0 0 8px rgba(101, 209, 138, .45);
    }
    .led.warn {
      background: #e0b35a;
      box-shadow: 0 0 0 3px rgba(224, 179, 90, .1), 0 0 8px rgba(224, 179, 90, .4);
    }
    .led.bad {
      background: #e0675a;
      box-shadow: 0 0 0 3px rgba(224, 103, 90, .1), 0 0 8px rgba(224, 103, 90, .45);
    }
    .led.off { background: #454741; box-shadow: none; }
    .led-tip {
      position: absolute;
      top: calc(100% + 8px);
      left: -2px;
      z-index: 30;
      width: max-content;
      max-width: min(320px, calc(100vw - 24px));
      padding: 9px 11px;
      border: 1px solid rgba(255, 255, 255, .14);
      border-radius: 8px;
      background: #1b1d18;
      box-shadow: 0 12px 32px rgba(0, 0, 0, .4);
      color: #e9e4d6;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 11px;
      font-weight: 400;
      line-height: 1.45;
      letter-spacing: 0;
      text-transform: none;
      white-space: normal;
      opacity: 0;
      transform: translateY(-4px) scale(.98);
      transform-origin: top left;
      transition: opacity .15s ease, transform .18s cubic-bezier(.2, .7, .2, 1);
      pointer-events: none;
    }
    .led-tip.is-open { opacity: 1; transform: none; }
    .led-tip::before {
      content: "";
      position: absolute;
      top: -5px;
      left: 15px;
      width: 8px;
      height: 8px;
      background: #1b1d18;
      border-top: 1px solid rgba(255, 255, 255, .14);
      border-left: 1px solid rgba(255, 255, 255, .14);
      transform: rotate(45deg);
    }
    .led-tip-row { display: flex; align-items: flex-start; gap: 7px; }
    .led-tip-row + .led-tip-row { margin-top: 5px; }
    .led-tip-row .led { margin-top: 3px; }
    .led-tip-row span:last-child { display: block; }
    .count { color: #cfc9b9; min-width: 52px; }

    .title-wrap {
      display: flex;
      align-items: center;
      flex: 1 1 auto;
      min-width: 0;
    }

    .title {
      appearance: none;
      -webkit-appearance: none;
      display: flex;
      align-items: center;
      gap: 6px;
      flex: 1 1 auto;
      min-width: 0;
      height: 28px;
      margin: 0;
      padding: 0 6px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: #f4f0e6;
      font: inherit;
      font-weight: 500;
      font-size: 13px;
      letter-spacing: .005em;
      text-align: left;
      cursor: pointer;
    }
    .title:hover { background: rgba(255, 255, 255, .075); }
    .title:focus-visible { outline: 2px solid #d0a64a; outline-offset: 0; }
    .title-text {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .title .chev {
      width: 13px;
      height: 13px;
      flex: none;
      color: #979284;
      transition: transform .15s ease;
    }
    .title[aria-expanded="true"] .chev { transform: rotate(180deg); }

    .menu {
      position: absolute;
      top: calc(100% - 4px);
      left: 8px;
      z-index: 40;
      display: flex;
      flex-direction: column;
      width: min(430px, calc(100vw - 16px));
      max-height: min(70vh, 560px);
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, .14);
      border-radius: 10px;
      background: #1b1d18;
      box-shadow: 0 18px 48px rgba(0, 0, 0, .48);
      color: #e9e4d6;
      pointer-events: auto;
      user-select: text;
      -webkit-user-select: text;
    }
    .menu[hidden] { display: none; }

    .menu-top {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 12px 8px;
    }
    .menu-current { flex: 1 1 auto; min-width: 0; }
    .menu-current-label {
      display: block;
      margin-bottom: 3px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9px;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: #979284;
    }
    .menu-current-title {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 13px;
      font-weight: 600;
      color: #f4f0e6;
    }

    .star-btn {
      appearance: none;
      -webkit-appearance: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 30px;
      height: 30px;
      margin: 0;
      padding: 0;
      border: 1px solid rgba(255, 255, 255, .14);
      border-radius: 7px;
      background: transparent;
      color: #979284;
      font: inherit;
      font-size: 16px;
      line-height: 1;
      cursor: pointer;
      flex: none;
    }
    .star-btn:hover { background: rgba(255, 255, 255, .07); color: #f1d18a; }
    .star-btn[aria-pressed="true"] {
      border-color: rgba(241, 209, 138, .4);
      background: rgba(241, 209, 138, .08);
      color: #f1d18a;
    }
    .star-btn:focus-visible { outline: 2px solid #d0a64a; outline-offset: 1px; }
    .star-btn:disabled { opacity: .35; cursor: default; pointer-events: none; }

    .menu-search { padding: 0 12px 9px; }
    .menu-input {
      width: 100%;
      height: 30px;
      padding: 0 10px;
      border: 1px solid rgba(255, 255, 255, .14);
      border-radius: 6px;
      background: #12130f;
      color: #eee9dc;
      font: inherit;
      font-size: 12.5px;
      outline: none;
    }
    .menu-input:focus {
      border-color: #d0a64a;
      box-shadow: 0 0 0 2px rgba(208, 166, 74, .18);
    }
    .menu-input::placeholder { color: #7c786c; }

    .menu-scroll {
      overflow-y: auto;
      padding: 0 6px 8px;
      overscroll-behavior: contain;
      scrollbar-width: thin;
    }
    .menu-heading {
      padding: 8px 8px 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9px;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: #979284;
    }
    .menu-section[hidden] { display: none; }
    .menu-section + .menu-section .menu-heading {
      margin-top: 4px;
      padding-top: 10px;
      border-top: 1px solid rgba(255, 255, 255, .08);
    }

    .menu-row {
      display: flex;
      align-items: center;
      gap: 4px;
      border-radius: 6px;
    }
    .menu-row:hover { background: rgba(255, 255, 255, .055); }
    .menu-row.is-current { background: rgba(208, 166, 74, .1); }

    .menu-app {
      appearance: none;
      -webkit-appearance: none;
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 1px;
      flex: 1 1 auto;
      min-width: 0;
      margin: 0;
      padding: 6px 8px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: #e9e4d6;
      font: inherit;
      text-align: left;
      cursor: pointer;
    }
    .menu-app:focus-visible { outline: 2px solid #d0a64a; outline-offset: -2px; }
    .menu-app-title {
      display: block;
      width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 12.5px;
    }
    .menu-row.is-current .menu-app-title { color: #f6e5b4; }
    .menu-app-dir {
      display: block;
      width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9.5px;
      color: #7f7b6e;
    }

    .row-star {
      appearance: none;
      -webkit-appearance: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 26px;
      height: 26px;
      margin: 0 2px 0 0;
      padding: 0;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: #6f6b60;
      font: inherit;
      font-size: 14px;
      line-height: 1;
      cursor: pointer;
      flex: none;
    }
    .row-star:hover { background: rgba(255, 255, 255, .08); color: #f1d18a; }
    .row-star[aria-pressed="true"] { color: #f1d18a; }
    .row-star:focus-visible { outline: 2px solid #d0a64a; outline-offset: 0; }

    .menu-empty {
      padding: 18px 12px;
      color: #979284;
      font-size: 12.5px;
      text-align: center;
    }
    .menu-empty[hidden] { display: none; }

    .actions { display: flex; align-items: center; gap: 2px; flex: 0 0 auto; }
    .btn {
      appearance: none;
      -webkit-appearance: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      height: 28px;
      margin: 0;
      padding: 0 9px;
      border: 1px solid transparent;
      border-radius: 6px;
      background: transparent;
      color: #cfc9b8;
      font: inherit;
      font-size: 12px;
      line-height: 1;
      cursor: pointer;
      white-space: nowrap;
    }
    .btn:hover { background: rgba(255, 255, 255, .075); color: #fff; }
    .btn:active { background: rgba(255, 255, 255, .11); }
    .btn:focus-visible { outline: 2px solid #d0a64a; outline-offset: 0; }
    .btn:disabled { opacity: .28; cursor: default; pointer-events: none; }
    .btn svg { width: 15px; height: 15px; flex: none; }
    .sep { width: 1px; height: 17px; background: rgba(255, 255, 255, .13); margin: 0 4px; }

    .peek {
      position: fixed;
      top: 0;
      right: 14px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      height: 19px;
      margin: 0;
      padding: 0 8px;
      border: 1px solid rgba(255, 255, 255, .14);
      border-top: 0;
      border-radius: 0 0 6px 6px;
      background: rgba(17, 18, 15, .85);
      color: #b9b3a4;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9px;
      letter-spacing: .12em;
      text-transform: uppercase;
      cursor: pointer;
      opacity: 0;
      transform: translateY(-4px);
      pointer-events: none;
      transition: opacity 160ms ease, transform 160ms ease;
      -webkit-backdrop-filter: blur(12px);
      backdrop-filter: blur(12px);
    }
    .peek.is-shown { opacity: .42; transform: none; pointer-events: auto; }
    .peek.is-shown:hover, .peek.is-shown:focus-visible { opacity: 1; }
    .peek:focus-visible { outline: 2px solid #d0a64a; outline-offset: 1px; }

    @media (max-width: 720px) {
      .bar { height: 40px; gap: 8px; padding: 0 4px 0 10px; }
      .label { display: none; }
      .btn { padding: 0 8px; }
      .count { min-width: 0; }
      .title { font-size: 12.5px; padding: 0 4px; }
      .menu {
        left: 4px;
        width: calc(100vw - 8px);
        max-height: calc(100vh - 56px);
      }
    }
    @media (max-width: 420px) {
      .leds { gap: 4px; padding: 0 5px; margin-left: -5px; }
      .count { font-size: 9px; }
      .peek-label { display: none; }
      .menu-app-dir { display: none; }
    }
    @media (prefers-reduced-motion: reduce) {
      .bar, .peek, .led-tip { transition: none; }
    }
  `;

  function boot() {
    if (document.body) {
      start();
    } else {
      document.addEventListener("DOMContentLoaded", start, { once: true });
    }
  }

  function start() {
    if (Array.isArray(window.__RIBBON_APPS__)) {
      mount(window.__RIBBON_APPS__);
      return;
    }

    var manifestUrl;
    try {
      manifestUrl = new URL("manifest.json", scriptBase).href;
    } catch (_) {
      return;
    }

    fetch(manifestUrl, { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        var apps = Array.isArray(data) ? data : data && data.apps;
        if (Array.isArray(apps) && apps.length) mount(apps);
      })
      .catch(function () {
        /* No manifest (for example, opened from file://): stay quiet. */
      });
  }

  function mount(rawApps) {
    var apps = rawApps.filter(function (app) {
      return app && typeof app.url === "string" && app.url;
    });
    if (!apps.length) return;

    var host = document.createElement("div");
    host.setAttribute("data-ribbon-host", "");
    host.style.cssText = [
      "position:fixed!important",
      "top:0!important",
      "right:0!important",
      "left:0!important",
      "width:100%!important",
      "height:auto!important",
      "margin:0!important",
      "padding:0!important",
      "border:0!important",
      "background:transparent!important",
      "z-index:2147483647!important",
      "display:block!important",
      "pointer-events:none!important",
      "isolation:isolate!important"
    ].join(";");

    var shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML =
      "<style>" + CSS + "</style>" +
      '<div class="bar" role="navigation" aria-label="App ribbon">' +
        '<div class="meta">' +
          '<span class="led-wrap">' +
            '<button class="leds" type="button" aria-label="Git status" aria-expanded="false" aria-describedby="led-tip">' +
              '<span class="led off" data-led="repo" aria-hidden="true"></span>' +
              '<span class="led off" data-led="sync" aria-hidden="true"></span>' +
            '</button>' +
            '<span class="led-tip" id="led-tip" role="tooltip" aria-hidden="true">' +
              '<span class="led-tip-row"><span class="led off" data-tip-led="repo" aria-hidden="true"></span><span data-tip-text="repo"></span></span>' +
              '<span class="led-tip-row"><span class="led off" data-tip-led="sync" aria-hidden="true"></span><span data-tip-text="sync"></span></span>' +
            '</span>' +
          '</span>' +
          '<span class="count"></span>' +
        '</div>' +
        '<div class="title-wrap">' +
          '<button class="title" type="button" aria-haspopup="dialog" aria-expanded="false" title="Show all apps">' +
            '<span class="title-text"></span>' +
            '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>' +
          '</button>' +
        '</div>' +
        '<div class="actions">' +
          '<button class="btn" type="button" data-act="prev" aria-label="Previous app" title="Previous app — [">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>' +
            '<span class="label">Back</span>' +
          '</button>' +
          '<button class="btn" type="button" data-act="next" aria-label="Next app" title="Next app — ]">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>' +
            '<span class="label">Next</span>' +
          '</button>' +
          '<button class="btn" type="button" data-act="random" aria-label="Random app" title="Random app — R">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 4l3 3-3 3"/><path d="M18 20l3-3-3-3"/><path d="M3 7h3c2 0 3.5 1 4.5 2.5l3 5C14.5 16 16 17 18 17h3"/><path d="M3 17h3c2 0 3.5-1 4.5-2.5l3-5C14.5 8 16 7 18 7h3"/></svg>' +
            '<span class="label">Random</span>' +
          '</button>' +
          '<button class="btn" type="button" data-act="reload" aria-label="Reload app" title="Reload app — Shift+R">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>' +
          '</button>' +
          '<span class="sep" aria-hidden="true"></span>' +
          '<button class="btn" type="button" data-act="hide" aria-label="Hide ribbon" title="Hide ribbon — H">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6L6 18"/><path d="M6 6l12 12"/></svg>' +
          '</button>' +
        '</div>' +
        '<div class="menu" hidden role="dialog" aria-label="All apps">' +
          '<div class="menu-top">' +
            '<div class="menu-current">' +
              '<span class="menu-current-label">Current app</span>' +
              '<span class="menu-current-title"></span>' +
            '</div>' +
            '<button class="star-btn" type="button" aria-pressed="false" aria-label="Add to favorites" title="Add to favorites">☆</button>' +
          '</div>' +
          '<div class="menu-search">' +
            '<input class="menu-input" type="search" placeholder="Search apps…" aria-label="Search apps" autocomplete="off" spellcheck="false">' +
          '</div>' +
          '<div class="menu-scroll">' +
            '<div class="menu-section" data-section="favorites" hidden>' +
              '<div class="menu-heading">Favorites</div>' +
              '<div class="menu-list" data-list="favorites"></div>' +
            '</div>' +
            '<div class="menu-section" data-section="all">' +
              '<div class="menu-heading">All apps</div>' +
              '<div class="menu-list" data-list="all"></div>' +
            '</div>' +
            '<div class="menu-empty" hidden>No apps match.</div>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<button class="peek" type="button" aria-label="Show ribbon" title="Show ribbon — H">' +
        '<span aria-hidden="true">▤</span><span class="peek-label">ribbon</span>' +
      '</button>';

    var bar = shadow.querySelector(".bar");
    var countEl = shadow.querySelector(".count");
    var titleButton = shadow.querySelector(".title");
    var titleText = shadow.querySelector(".title-text");
    var peekEl = shadow.querySelector(".peek");
    var ledRepo = shadow.querySelector('[data-led="repo"]');
    var ledSync = shadow.querySelector('[data-led="sync"]');
    var ledsButton = shadow.querySelector(".leds");
    var ledWrap = ledsButton.parentNode;
    var ledTip = shadow.querySelector(".led-tip");
    var tipRepoDot = ledTip.querySelector('[data-tip-led="repo"]');
    var tipSyncDot = ledTip.querySelector('[data-tip-led="sync"]');
    var tipRepoText = ledTip.querySelector('[data-tip-text="repo"]');
    var tipSyncText = ledTip.querySelector('[data-tip-text="sync"]');
    var buttons = shadow.querySelectorAll("button[data-act]");

    var menuEl = shadow.querySelector(".menu");
    var menuCurrentTitle = shadow.querySelector(".menu-current-title");
    var starCurrent = shadow.querySelector(".star-btn");
    var searchInput = shadow.querySelector(".menu-input");
    var menuFavSection = shadow.querySelector('[data-section="favorites"]');
    var menuAllSection = shadow.querySelector('[data-section="all"]');
    var menuFavList = shadow.querySelector('[data-list="favorites"]');
    var menuAllList = shadow.querySelector('[data-list="all"]');
    var menuAllHeading = menuAllSection.querySelector(".menu-heading");
    var menuEmpty = shadow.querySelector(".menu-empty");

    var here = normalizePath(location.pathname);
    var index = -1;
    for (var i = 0; i < apps.length; i += 1) {
      if (normalizePath(entryPath(apps[i])) === here) {
        index = i;
        break;
      }
    }
    var exact = index >= 0;
    if (index < 0) {
      var bestLength = -1;
      for (var j = 0; j < apps.length; j += 1) {
        var candidate = normalizePath(entryPath(apps[j]));
        if (here.indexOf(candidate) === 0 && candidate.length > bestLength) {
          bestLength = candidate.length;
          index = j;
        }
      }
    }

    var pageTitle = (document.title || "").trim();
    var currentTitle = exact && apps[index]
      ? apps[index].title
      : pageTitle || (apps[index] && apps[index].title) || "Untitled";

    var favorites = readFavorites();
    var menuOpen = false;

    titleText.textContent = currentTitle;
    titleButton.title = "Show all apps";
    menuCurrentTitle.textContent = currentTitle;
    countEl.textContent = (index >= 0 ? pad(index + 1, apps.length) : "—") + " / " + pad(apps.length, apps.length);
    setGit(apps[index] && apps[index].git);
    updateCurrentStar();

    if (apps.length < 2) {
      for (var k = 0; k < buttons.length; k += 1) {
        var act = buttons[k].getAttribute("data-act");
        if (act !== "hide") buttons[k].disabled = true;
      }
    }

    var manualHidden = readHidden();
    var autoHidden = false;
    var lastTargets = new Map();
    var tipPinned = false;
    var tipTimer = 0;
    var hoverCapable = window.matchMedia("(hover: hover)").matches;

    function applyState() {
      var gone = manualHidden || autoHidden;
      if (gone) {
        closeTip();
        closeMenu(false);
      }
      bar.classList.toggle("is-gone", gone);
      if (gone) bar.setAttribute("inert", "");
      else bar.removeAttribute("inert");
      peekEl.classList.toggle("is-shown", manualHidden);
      peekEl.tabIndex = manualHidden ? 0 : -1;
    }

    function setManual(hidden) {
      manualHidden = hidden;
      if (hidden) autoHidden = false;
      else lastTargets.clear();
      try {
        sessionStorage.setItem(STORAGE_KEY, hidden ? "1" : "0");
      } catch (_) {}
      applyState();
    }

    function go(direction) {
      if (apps.length < 2) return;
      var target;
      if (index < 0) {
        target = direction > 0 ? 0 : apps.length - 1;
      } else {
        target = (index + direction + apps.length) % apps.length;
        if (target === index) return;
      }
      location.assign(apps[target].url);
    }

    function random() {
      if (apps.length < 2) return;
      var choices = apps.length - (index >= 0 ? 1 : 0);
      var pick = Math.floor(Math.random() * choices);
      if (index >= 0 && pick >= index) pick += 1;
      location.assign(apps[pick].url);
    }

    function reloadApp() {
      closeMenu(false);
      location.reload();
    }

    function appKey(app) {
      return app ? app.dir || app.path || app.url || "" : "";
    }

    function readFavorites() {
      try {
        var stored = JSON.parse(localStorage.getItem("ribbon:favorites") || "[]");
        if (Array.isArray(stored)) {
          return new Set(stored.filter(function (item) {
            return typeof item === "string";
          }));
        }
      } catch (_) {}
      return new Set();
    }

    function saveFavorites() {
      try {
        localStorage.setItem("ribbon:favorites", JSON.stringify(Array.from(favorites)));
      } catch (_) {}
    }

    function isFavorite(app) {
      return !!app && favorites.has(appKey(app));
    }

    function currentApp() {
      return index >= 0 ? apps[index] : null;
    }

    function updateCurrentStar() {
      var app = currentApp();
      var favorite = isFavorite(app);
      var name = app ? app.title || "this app" : "this app";
      var label = (favorite ? "Remove " : "Add ") +
        name + (favorite ? " from favorites" : " to favorites");
      starCurrent.disabled = !app;
      starCurrent.setAttribute("aria-pressed", favorite ? "true" : "false");
      starCurrent.textContent = favorite ? "★" : "☆";
      starCurrent.title = label;
      starCurrent.setAttribute("aria-label", label);
    }

    function favoriteRow(app, appIndex) {
      var favorite = isFavorite(app);
      var row = document.createElement("div");
      row.className = "menu-row" + (appIndex === index ? " is-current" : "");

      var open = document.createElement("button");
      open.type = "button";
      open.className = "menu-app";
      open.setAttribute("data-app", String(appIndex));
      if (appIndex === index) open.setAttribute("aria-current", "true");

      var title = document.createElement("span");
      title.className = "menu-app-title";
      title.textContent = app.title || "Untitled";

      var path = app.path || app.dir || "";
      var dir = document.createElement("span");
      dir.className = "menu-app-dir";
      dir.textContent = path && path !== "." ? "/" + path : "/";

      open.appendChild(title);
      open.appendChild(dir);

      var star = document.createElement("button");
      star.type = "button";
      star.className = "row-star";
      star.setAttribute("data-star", appKey(app));
      star.setAttribute("aria-pressed", favorite ? "true" : "false");
      star.title = favorite ? "Remove from favorites" : "Add to favorites";
      star.setAttribute(
        "aria-label",
        (favorite ? "Remove " : "Add ") +
          (app.title || "app") +
          (favorite ? " from favorites" : " to favorites")
      );
      star.textContent = favorite ? "★" : "☆";

      row.appendChild(open);
      row.appendChild(star);
      return row;
    }

    function matchesQuery(app, query) {
      if (!query) return true;
      var haystack = String(app.title || "").toLowerCase() +
        " " + String(app.path || app.dir || "").toLowerCase();
      return haystack.indexOf(query) !== -1;
    }

    function renderMenu(query) {
      var needle = (query || "").trim().toLowerCase();
      menuFavList.textContent = "";
      menuAllList.textContent = "";
      var favoriteCount = 0;
      var otherCount = 0;

      apps.forEach(function (app, appIndex) {
        if (!matchesQuery(app, needle)) return;
        if (isFavorite(app)) {
          menuFavList.appendChild(favoriteRow(app, appIndex));
          favoriteCount += 1;
        } else {
          menuAllList.appendChild(favoriteRow(app, appIndex));
          otherCount += 1;
        }
      });

      menuFavSection.hidden = favoriteCount === 0;
      menuAllSection.hidden = otherCount === 0;
      menuEmpty.hidden = favoriteCount + otherCount > 0;
      menuAllHeading.textContent = favoriteCount ? "Other apps" : "All apps";
    }

    function openMenu() {
      if (!apps.length) return;
      if (menuOpen) {
        searchInput.focus();
        searchInput.select();
        return;
      }
      menuOpen = true;
      menuEl.hidden = false;
      titleButton.setAttribute("aria-expanded", "true");
      searchInput.value = "";
      renderMenu("");
      updateCurrentStar();
      requestAnimationFrame(function () {
        searchInput.focus();
        searchInput.select();
      });
    }

    function closeMenu(returnFocus) {
      if (!menuOpen) return;
      menuOpen = false;
      menuEl.hidden = true;
      titleButton.setAttribute("aria-expanded", "false");
      if (returnFocus) titleButton.focus();
    }

    function toggleMenu() {
      if (menuOpen) closeMenu(true);
      else openMenu();
    }

    function toggleFavorite(app, focusStar) {
      var key = appKey(app);
      if (!key) return;
      if (favorites.has(key)) favorites.delete(key);
      else favorites.add(key);
      saveFavorites();
      renderMenu(searchInput.value);
      updateCurrentStar();
      if (focusStar) {
        var stars = menuEl.querySelectorAll("[data-star]");
        for (var i = 0; i < stars.length; i += 1) {
          if (stars[i].getAttribute("data-star") === key) {
            stars[i].focus();
            break;
          }
        }
      }
    }

    function setGit(git) {
      var repo = !!(git && git.repo);
      var state = (git && git.state) || "";
      var repoClass = repo ? "ok" : "off";
      var syncClass = "off";
      if (repo) {
        if (state === "ahead") syncClass = "bad";
        else if (state === "dirty" || state === "no-upstream" || state === "detached" || state === "no-commits") syncClass = "warn";
        else if (state === "error") syncClass = "off";
        else syncClass = "ok";
      }

      ledRepo.className = "led " + repoClass;
      ledSync.className = "led " + syncClass;
      tipRepoDot.className = "led " + repoClass;
      tipSyncDot.className = "led " + syncClass;

      var repoText = repoTip(git);
      var syncText = gitTip(git);
      tipRepoText.textContent = repoText;
      tipSyncText.textContent = syncText;
      ledsButton.setAttribute("aria-label", repoText + ". " + syncText);
    }

    function repoTip(git) {
      if (!git || !git.repo) {
        return git && git.state === "error"
          ? "Git status unavailable"
          : "Not a Git repository";
      }
      return "Git repository" + (git.branch ? " — " + git.branch : "");
    }

    function gitTip(git) {
      if (!git || !git.repo) return "No push status";
      var bits = [];
      if (git.state === "ahead") {
        var count = git.ahead || 1;
        bits.push(count + " commit" + (count === 1 ? "" : "s") + " not pushed");
      } else if (git.state === "no-upstream") {
        bits.push("No upstream branch");
      } else if (git.state === "detached") {
        bits.push("Detached HEAD");
      } else if (git.state === "no-commits") {
        bits.push("No commits yet");
      } else if (git.state === "dirty") {
        bits.push("Uncommitted changes");
      } else if (git.state === "error") {
        bits.push("Git status unavailable");
      } else {
        bits.push("All changes pushed");
      }
      if (git.dirty && git.state !== "dirty") bits.push("uncommitted changes");
      if (git.behind) bits.push(git.behind + " behind");
      return bits.join(" · ");
    }

    function openTip(pin) {
      if (pin) tipPinned = true;
      ledTip.classList.add("is-open");
      ledTip.setAttribute("aria-hidden", "false");
      ledsButton.setAttribute("aria-expanded", "true");
      if (tipTimer) {
        clearTimeout(tipTimer);
        tipTimer = 0;
      }
      if (!hoverCapable && tipPinned) {
        tipTimer = setTimeout(closeTip, 5000);
      }
    }

    function closeTip() {
      tipPinned = false;
      ledTip.classList.remove("is-open");
      ledTip.setAttribute("aria-hidden", "true");
      ledsButton.setAttribute("aria-expanded", "false");
      if (tipTimer) {
        clearTimeout(tipTimer);
        tipTimer = 0;
      }
    }

    function toggleTip() {
      if (ledTip.classList.contains("is-open") && tipPinned) closeTip();
      else openTip(true);
    }

    function closeTipIfUnpinned() {
      if (!tipPinned) closeTip();
    }

    shadow.addEventListener("click", function (event) {
      var button = event.target && event.target.closest
        ? event.target.closest("button[data-act]")
        : null;
      if (!button) return;
      var action = button.getAttribute("data-act");
      if (action === "prev") go(-1);
      else if (action === "next") go(1);
      else if (action === "random") random();
      else if (action === "reload") reloadApp();
      else if (action === "hide") setManual(true);
    });
    peekEl.addEventListener("click", function () {
      setManual(false);
    });

    titleButton.addEventListener("click", toggleMenu);
    starCurrent.addEventListener("click", function () {
      var app = currentApp();
      if (app) toggleFavorite(app, false);
      starCurrent.focus();
    });
    searchInput.addEventListener("input", function () {
      renderMenu(searchInput.value);
    });
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeMenu(true);
        return;
      }
      if (event.key === "Enter") {
        var first = menuEl.querySelector(".menu-app");
        if (first) {
          event.preventDefault();
          location.assign(apps[Number(first.getAttribute("data-app"))].url);
        }
        return;
      }
      if (event.key === "ArrowDown") {
        var first = menuEl.querySelector(".menu-app");
        if (first) {
          event.preventDefault();
          first.focus();
        }
      }
    });
    menuEl.addEventListener("click", function (event) {
      var star = event.target && event.target.closest
        ? event.target.closest(".row-star")
        : null;
      if (star) {
        for (var i = 0; i < apps.length; i += 1) {
          if (appKey(apps[i]) === star.getAttribute("data-star")) {
            toggleFavorite(apps[i], true);
            break;
          }
        }
        return;
      }

      var row = event.target && event.target.closest
        ? event.target.closest(".menu-app")
        : null;
      if (row) {
        location.assign(apps[Number(row.getAttribute("data-app"))].url);
      }
    });
    document.addEventListener("pointerdown", function (event) {
      if (!menuOpen) return;
      var path = event.composedPath ? event.composedPath() : [];
      if (path.indexOf(menuEl) !== -1 || path.indexOf(titleButton) !== -1) return;
      closeMenu(false);
    }, true);

    ledsButton.addEventListener("click", function (event) {
      event.stopPropagation();
      toggleTip();
    });
    ledsButton.addEventListener("pointerenter", function () {
      if (hoverCapable) openTip(false);
    });
    ledsButton.addEventListener("pointerleave", closeTipIfUnpinned);
    ledsButton.addEventListener("focus", function () {
      openTip(false);
    });
    ledsButton.addEventListener("blur", closeTipIfUnpinned);
    document.addEventListener("pointerdown", function (event) {
      if (!ledTip.classList.contains("is-open")) return;
      var path = event.composedPath ? event.composedPath() : [];
      if (path.indexOf(ledWrap) !== -1) return;
      closeTip();
    }, true);

    var pending = null;
    function processScroll() {
      var event = pending;
      pending = null;
      if (manualHidden) return;
      if (event && event.target && menuEl.contains(event.target)) return;

      var target = event && event.target;
      if (
        target === document ||
        target === window ||
        target === document.documentElement ||
        target === document.body
      ) {
        target = null;
      }
      var y = target ? target.scrollTop : scrollY();
      var hasPrevious = lastTargets.has(target);
      var previous = hasPrevious ? lastTargets.get(target) : y;
      var delta = y - previous;

      if (Math.abs(delta) < 10) {
        if (!hasPrevious) lastTargets.set(target, y);
        return;
      }

      if (y <= 8) autoHidden = false;
      else if (delta > 0 && y > 48) autoHidden = true;
      else if (delta < 0) autoHidden = false;

      lastTargets.set(target, y);
      applyState();
    }

    function onScroll(event) {
      if (pending) return;
      pending = event;
      requestAnimationFrame(processScroll);
    }

    window.addEventListener("keydown", function (event) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      var target = event.target;
      if (
        target &&
        (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
      ) {
        return;
      }

      var key = event.key;
      if (key === "Escape" && menuOpen) {
        closeMenu(true);
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (key === "/") {
        openMenu();
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (menuOpen) return;
      if (key === "Escape" && ledTip.classList.contains("is-open")) {
        closeTip();
        event.preventDefault();
        event.stopPropagation();
        return;
      }

      var handled = true;
      if (key === "[") go(-1);
      else if (key === "]") go(1);
      else if (key === "r" || key === "R") {
        if (event.shiftKey) reloadApp();
        else random();
      } else if (key === "h" || key === "H") toggleHidden();
      else handled = false;

      if (handled) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);

    function toggleHidden() {
      if (!manualHidden && autoHidden) {
        autoHidden = false;
        applyState();
        return;
      }
      setManual(!manualHidden);
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    document.addEventListener("scroll", onScroll, { passive: true, capture: true });

    window.__ribbon = {
      show: function () { setManual(false); },
      hide: function () { setManual(true); },
      toggle: function () { toggleHidden(); },
      prev: function () { go(-1); },
      next: function () { go(1); },
      random: random,
      apps: apps
    };

    applyState();
    document.documentElement.appendChild(host);
  }

  function normalizePath(path) {
    var value = path;
    try {
      value = decodeURIComponent(path);
    } catch (_) {}
    value = value.replace(/\/index\.html?$/i, "/");
    if (value.charAt(value.length - 1) !== "/" && !/\.[a-z0-9]+$/i.test(value)) {
      value += "/";
    }
    return value;
  }

  function entryPath(app) {
    try {
      return new URL(app.url, location.href).pathname;
    } catch (_) {
      return app.url;
    }
  }

  function pad(number, total) {
    var width = String(total).length;
    var value = String(number);
    while (value.length < width) value = "0" + value;
    return value;
  }

  function readHidden() {
    try {
      return sessionStorage.getItem(STORAGE_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function scrollY() {
    return window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0;
  }

  boot();
})();

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

    .title {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 500;
      font-size: 13px;
      letter-spacing: .005em;
      color: #f4f0e6;
      padding-right: 4px;
    }

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
      .title { font-size: 12.5px; }
    }
    @media (max-width: 420px) {
      .leds { gap: 4px; padding: 0 5px; margin-left: -5px; }
      .count { font-size: 9px; }
      .peek-label { display: none; }
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
        '<div class="title"></div>' +
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
          '<span class="sep" aria-hidden="true"></span>' +
          '<button class="btn" type="button" data-act="hide" aria-label="Hide ribbon" title="Hide ribbon — H">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6L6 18"/><path d="M6 6l12 12"/></svg>' +
          '</button>' +
        '</div>' +
      '</div>' +
      '<button class="peek" type="button" aria-label="Show ribbon" title="Show ribbon — H">' +
        '<span aria-hidden="true">▤</span><span class="peek-label">ribbon</span>' +
      '</button>';

    var bar = shadow.querySelector(".bar");
    var countEl = shadow.querySelector(".count");
    var titleEl = shadow.querySelector(".title");
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

    titleEl.textContent = currentTitle;
    titleEl.title = currentTitle;
    countEl.textContent = (index >= 0 ? pad(index + 1, apps.length) : "—") + " / " + pad(apps.length, apps.length);
    setGit(apps[index] && apps[index].git);

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
      if (gone) closeTip();
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
      else if (action === "hide") setManual(true);
    });
    peekEl.addEventListener("click", function () {
      setManual(false);
    });

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
      if (key === "Escape" && ledTip.classList.contains("is-open")) {
        closeTip();
        event.preventDefault();
        event.stopPropagation();
        return;
      }

      var handled = true;
      if (key === "[") go(-1);
      else if (key === "]") go(1);
      else if (key === "r" || key === "R") random();
      else if (key === "h" || key === "H") toggleHidden();
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

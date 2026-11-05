/* Ribbon — a floating, auto-hiding switcher for a folder of HTML apps.
 *
 * Normally injected by ribbon.py. It can also be included by hand:
 *   <script src="/__ribbon/ribbon.js" defer></script>
 * or, with no server, provide the list yourself before the script runs:
 *   window.__RIBBON_APPS__ = [{ url: "/app/", title: "App" }];
 */
(function () {
  "use strict"

  if (window.__RIBBON_MOUNTED__) return
  if (window.self !== window.top) return
  window.__RIBBON_MOUNTED__ = true

  const scriptEl = document.currentScript || document.querySelector("script[data-ribbon]")
  let scriptBase = "/__ribbon/"
  if (scriptEl && scriptEl.src) {
    try {
      scriptBase = new URL(".", scriptEl.src).href
    } catch (_) { /* keep the default base */ }
  }
  const CACHE_KEY = "ribbon:apps:" + scriptBase
  const DECK_KEY = "ribbon:deck:" + scriptBase
  const CHANNEL_KEY = "ribbon:channel:" + scriptBase

  const STORAGE_KEY = "ribbon:hidden"
  const BAR_HEIGHT = 40
  const CSS = `
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
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 1px;
      height: 28px;
      margin: 0 0 0 -6px;
      padding: 0 3px;
      border-radius: 6px;
      background: transparent;
    }
    .led-btn {
      appearance: none;
      -webkit-appearance: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 28px;
      margin: 0;
      padding: 0;
      border: 0;
      border-radius: 4px;
      background: transparent;
      font: inherit;
      cursor: pointer;
      touch-action: manipulation;
    }
    .led-btn:hover { background: rgba(255, 255, 255, .08); }
    .led-btn:focus-visible { outline: 2px solid #d0a64a; outline-offset: 0; }
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
      gap: 4px;
      flex: 1 1 auto;
      min-width: 0;
    }

    .title-star {
      width: 26px;
      height: 26px;
      border-color: transparent;
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
    .menu-current-meta {
      display: block;
      margin-top: 3px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9.5px;
      color: #8f8a7c;
    }

    .menu-current-tools {
      display: flex;
      align-items: center;
      gap: 5px;
      padding: 0 12px 9px;
    }
    .menu-current-hint {
      flex: 1 1 auto;
      overflow: hidden;
      text-align: right;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 8.5px;
      letter-spacing: .04em;
      color: #6f6b60;
    }
    .tool-btn {
      appearance: none;
      -webkit-appearance: none;
      height: 24px;
      padding: 0 9px;
      border: 1px solid rgba(255, 255, 255, .12);
      border-radius: 5px;
      background: transparent;
      color: #a9a496;
      font: inherit;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 10px;
      letter-spacing: .04em;
      cursor: pointer;
      flex: none;
    }
    .tool-btn:hover { background: rgba(255, 255, 255, .07); color: #e9e4d6; }
    .tool-btn[aria-pressed="true"] {
      border-color: rgba(241, 209, 138, .4);
      background: rgba(241, 209, 138, .08);
      color: #f1d18a;
    }
    .tool-btn:focus-visible { outline: 2px solid #d0a64a; outline-offset: 0; }
    .tool-btn:disabled { opacity: .35; cursor: default; pointer-events: none; }

    .menu-channels {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      padding: 0 12px 9px;
    }
    .chip {
      appearance: none;
      -webkit-appearance: none;
      height: 23px;
      padding: 0 8px;
      border: 1px solid rgba(255, 255, 255, .12);
      border-radius: 999px;
      background: transparent;
      color: #a9a496;
      font: inherit;
      font-size: 10.5px;
      cursor: pointer;
    }
    .chip:hover { background: rgba(255, 255, 255, .07); color: #e9e4d6; }
    .chip[aria-pressed="true"] {
      border-color: rgba(208, 166, 74, .45);
      background: rgba(208, 166, 74, .12);
      color: #f1d18a;
    }
    .chip:focus-visible { outline: 2px solid #d0a64a; outline-offset: 0; }
    .chip-count {
      margin-left: 5px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9px;
      color: #7f7b6e;
    }
    .chip[aria-pressed="true"] .chip-count { color: #c9a95e; }

    .menu-app-flag {
      margin-left: 6px;
      padding: 0 4px;
      border: 1px solid currentcolor;
      border-radius: 3px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 8px;
      letter-spacing: .05em;
      color: #c9a95e;
      vertical-align: 1px;
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

    .menu-leds {
      display: flex;
      align-items: center;
      gap: 4px;
      margin: 0 0 0 8px;
      flex: none;
    }
    .menu-leds .led { width: 7px; height: 7px; box-shadow: none; }
    .menu-leds .led.ok { box-shadow: 0 0 5px rgba(101, 209, 138, .45); }
    .menu-leds .led.warn { box-shadow: 0 0 5px rgba(224, 179, 90, .4); }
    .menu-leds .led.bad { box-shadow: 0 0 5px rgba(224, 103, 90, .45); }

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
    .menu-app-glyph {
      display: inline-grid;
      place-items: center;
      min-width: 22px;
      height: 15px;
      margin-right: 7px;
      padding: 0 4px;
      border: 1px solid currentcolor;
      border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 8px;
      font-weight: 700;
      letter-spacing: .03em;
      vertical-align: 1px;
    }
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

    .row-delete {
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
      font-size: 12px;
      line-height: 1;
      cursor: pointer;
      flex: none;
    }
    .row-delete:hover { background: rgba(224, 103, 90, .16); color: #f0a79d; }
    .row-delete:focus-visible { outline: 2px solid #d0a64a; outline-offset: 0; }

    .delete-overlay {
      position: fixed;
      inset: 0;
      z-index: 110;
      display: grid;
      place-items: center;
      padding: 18px;
      background: rgba(8, 9, 7, .62);
      -webkit-backdrop-filter: blur(3px);
      backdrop-filter: blur(3px);
      pointer-events: auto;
    }
    .delete-overlay[hidden] { display: none; }

    .delete-dialog {
      width: min(500px, 100%);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, .16);
      border-radius: 12px;
      background: #1b1d18;
      box-shadow: 0 30px 80px rgba(0, 0, 0, .55);
      color: #e9e4d6;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 13px;
      line-height: 1.45;
      user-select: text;
      -webkit-user-select: text;
    }

    .delete-head {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      padding: 14px 16px 11px;
      border-bottom: 1px solid rgba(255, 255, 255, .1);
    }
    .delete-heading { flex: 1 1 auto; min-width: 0; }
    .delete-kicker {
      margin-bottom: 3px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9px;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: #e0675a;
    }
    .delete-title { font-size: 15px; font-weight: 600; color: #f4f0e6; }

    .delete-body {
      display: grid;
      gap: 12px;
      padding: 14px 16px;
    }
    .delete-warn { margin: 0; }
    .delete-path {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 11px;
      color: #979284;
      word-break: break-all;
    }
    .delete-command-label {
      margin-bottom: 5px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9px;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: #979284;
    }
    .delete-command {
      margin: 0;
      padding: 10px 12px;
      border: 1px solid rgba(255, 255, 255, .12);
      border-radius: 8px;
      background: #11130f;
      color: #f0c7bf;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 11.5px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-all;
    }
    .delete-note { color: #979284; font-size: 11.5px; }

    .delete-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 11px 16px;
      border-top: 1px solid rgba(255, 255, 255, .1);
    }
    .delete-status {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #979284;
      font-size: 11px;
    }
    .delete-status.is-bad { color: #e0897e; }
    .btn.delete-primary {
      border-color: rgba(224, 103, 90, .55);
      background: #c95548;
      color: #fff;
      font-weight: 600;
    }
    .btn.delete-primary:hover { background: #d96456; color: #fff; }
    .btn.delete-primary:disabled { opacity: .5; cursor: default; }

    .menu-empty {
      padding: 18px 12px;
      color: #979284;
      font-size: 12.5px;
      text-align: center;
    }
    .menu-empty[hidden] { display: none; }

    .git-overlay {
      position: fixed;
      inset: 0;
      z-index: 100;
      display: grid;
      place-items: center;
      padding: 18px;
      background: rgba(8, 9, 7, .62);
      -webkit-backdrop-filter: blur(3px);
      backdrop-filter: blur(3px);
      pointer-events: auto;
    }
    .git-overlay[hidden] { display: none; }

    .git-dialog {
      width: min(560px, 100%);
      max-height: min(86vh, 720px);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      border: 1px solid rgba(255, 255, 255, .16);
      border-radius: 12px;
      background: #1b1d18;
      box-shadow: 0 30px 80px rgba(0, 0, 0, .55);
      color: #e9e4d6;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      font-size: 13px;
      line-height: 1.45;
      user-select: text;
      -webkit-user-select: text;
    }

    .git-head {
      display: flex;
      align-items: flex-start;
      gap: 12px;
      padding: 14px 16px 11px;
      border-bottom: 1px solid rgba(255, 255, 255, .1);
    }
    .git-heading { flex: 1 1 auto; min-width: 0; }
    .git-kicker {
      margin-bottom: 3px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9px;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: #979284;
    }
    .git-title { font-size: 15px; font-weight: 600; color: #f4f0e6; }
    .git-close {
      appearance: none;
      -webkit-appearance: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      margin: -2px -4px 0 0;
      padding: 0;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: #979284;
      font: inherit;
      font-size: 14px;
      cursor: pointer;
      flex: none;
    }
    .git-close:hover { background: rgba(255, 255, 255, .08); color: #fff; }
    .git-close:focus-visible { outline: 2px solid #d0a64a; outline-offset: 0; }

    .git-body {
      overflow-y: auto;
      padding: 14px 16px;
    }

    .git-summary { display: grid; gap: 3px; }
    .git-summary-row { display: flex; align-items: baseline; gap: 8px; }
    .git-summary-label {
      flex: 0 0 76px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9px;
      letter-spacing: .1em;
      text-transform: uppercase;
      color: #979284;
    }
    .git-summary-value {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 12px;
      color: #e9e4d6;
    }

    .git-files {
      max-height: 150px;
      margin-top: 12px;
      padding: 5px 0;
      overflow-y: auto;
      border: 1px solid rgba(255, 255, 255, .1);
      border-radius: 7px;
      background: #12130f;
    }
    .git-file {
      display: flex;
      align-items: baseline;
      gap: 7px;
      padding: 2px 9px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 10.5px;
    }
    .git-file-code { flex: none; width: 20px; color: #e0b35a; }
    .git-file-path { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #cfc9b9; }
    .git-file-more { padding: 4px 9px 1px; color: #7f7b6e; font-size: 10.5px; }

    .git-warnings {
      margin-top: 12px;
      padding: 9px 11px;
      border: 1px solid rgba(224, 179, 90, .35);
      border-radius: 7px;
      background: rgba(224, 179, 90, .08);
      color: #e8c982;
      font-size: 11.5px;
    }
    .git-warning + .git-warning { margin-top: 4px; }

    .git-field { display: block; margin-top: 14px; }
    .git-field[hidden] { display: none; }
    .git-label {
      display: block;
      margin-bottom: 5px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 9px;
      letter-spacing: .1em;
      text-transform: uppercase;
      color: #979284;
    }
    .git-input {
      width: 100%;
      height: 32px;
      padding: 0 10px;
      border: 1px solid rgba(255, 255, 255, .14);
      border-radius: 6px;
      background: #12130f;
      color: #eee9dc;
      font: inherit;
      font-size: 12.5px;
      outline: none;
    }
    .git-input:focus {
      border-color: #d0a64a;
      box-shadow: 0 0 0 2px rgba(208, 166, 74, .18);
    }
    .git-textarea {
      height: auto;
      min-height: 96px;
      padding: 8px 10px;
      resize: vertical;
      line-height: 1.5;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 11.5px;
    }
    .git-hint {
      display: block;
      margin-top: 5px;
      color: #8f8a7c;
      font-size: 10.5px;
      line-height: 1.4;
    }

    .git-radios { display: flex; gap: 18px; padding: 3px 0 1px; }
    .git-radio { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: #cfc9b8; cursor: pointer; }
    .git-radio input { accent-color: #d0a64a; }

    .git-check {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      margin-top: 14px;
      font-size: 12.5px;
      color: #cfc9b8;
      cursor: pointer;
    }
    .git-check[hidden] { display: none; }
    .git-check input { margin-top: 2px; accent-color: #d0a64a; }

    .git-note {
      margin-top: 12px;
      padding: 9px 11px;
      border: 1px solid rgba(255, 255, 255, .1);
      border-radius: 7px;
      background: rgba(255, 255, 255, .03);
      color: #a9a496;
      font-size: 11.5px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .git-output {
      margin: 12px 0 0;
      padding: 9px 11px;
      max-height: 170px;
      overflow: auto;
      border: 1px solid rgba(255, 255, 255, .1);
      border-radius: 7px;
      background: #12130f;
      color: #d8d2c2;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 10.5px;
      line-height: 1.5;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .git-output[hidden] { display: none; }

    .git-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 11px 16px;
      border-top: 1px solid rgba(255, 255, 255, .1);
    }
    .git-status {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #979284;
      font-size: 11px;
    }
    .git-status.is-good { color: #8dd9a8; }
    .git-status.is-bad { color: #e0897e; }
    .btn.git-primary {
      border-color: rgba(208, 166, 74, .55);
      background: #d0a64a;
      color: #17180f;
      font-weight: 600;
    }
    .btn.git-primary:hover { background: #dfb45a; color: #17180f; }
    .btn.git-primary:disabled { opacity: .5; cursor: default; }

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
    .btn.is-active {
      background: rgba(208, 166, 74, .17);
      color: #f4ecd7;
    }
    .btn:focus-visible { outline: 2px solid #d0a64a; outline-offset: 0; }
    .btn:disabled { opacity: .28; cursor: default; pointer-events: none; }
    .btn svg { width: 15px; height: 15px; flex: none; }
    .sep { width: 1px; height: 17px; background: rgba(255, 255, 255, .13); margin: 0 4px; }

    .card-overlay {
      position: fixed;
      inset: 40px 0 0;
      z-index: 90;
      overflow: hidden;
      background: #171814;
      pointer-events: auto;
    }
    .card-overlay[hidden] { display: none; }

    .card-frame {
      display: block;
      width: 100%;
      height: 100%;
      margin: 0;
      border: 0;
      background: #171814;
      transform-origin: left center;
      backface-visibility: hidden;
      -webkit-backface-visibility: hidden;
    }

    .card-close {
      position: absolute;
      top: 14px;
      right: 16px;
      z-index: 2;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      height: 28px;
      margin: 0;
      padding: 0 11px;
      border: 1px solid rgba(255, 255, 255, .16);
      border-radius: 999px;
      background: rgba(18, 19, 16, .72);
      color: #ded8c8;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 10px;
      letter-spacing: .08em;
      text-transform: uppercase;
      cursor: pointer;
      pointer-events: auto;
      -webkit-backdrop-filter: blur(10px);
      backdrop-filter: blur(10px);
    }
    .card-close:hover { background: rgba(30, 31, 26, .92); color: #fff; }
    .card-close:focus-visible { outline: 2px solid #d0a64a; outline-offset: 2px; }

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
      .git-overlay { padding: 8px; }
      .git-dialog { max-height: calc(100vh - 16px); }
      .card-close { top: 8px; right: 8px; }
    }
    @media (max-width: 420px) {
      .leds { gap: 0; padding: 0 2px; margin-left: -5px; }
      .count { font-size: 9px; }
      .peek-label { display: none; }
      .menu-app-dir { display: none; }
    }
    @media (prefers-reduced-motion: reduce) {
      .bar, .peek, .led-tip { transition: none; }
    }
  `

  function boot() {
    if (document.body) {
      start()
    } else {
      document.addEventListener("DOMContentLoaded", start, { once: true })
    }
  }

  function start() {
    if (Array.isArray(window.__RIBBON_APPS__)) {
      mount(window.__RIBBON_APPS__)
      return
    }

    let manifestUrl
    try {
      manifestUrl = new URL("manifest.json", scriptBase).href
    } catch (_) {
      return
    }

    // Draw the bar from the last list straight away, then refresh it when the
    // manifest arrives. Switching apps no longer waits on the manifest first.
    const cached = readCachedApps()
    let update = cached ? mount(cached) : null

    fetch(manifestUrl, { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status)
        return response.json()
      })
      .then(function (data) {
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
        if (update) update(apps, meta)
        else update = mount(apps, meta) || null
      })
      .catch(function () {
        /* No manifest (for example, opened from file://): stay quiet. */
      })
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

  function mount(rawApps, meta) {
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

    const host = document.createElement("div")
    host.setAttribute("data-ribbon-host", "")
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
    ].join(";")

    const shadow = host.attachShadow({ mode: "open" })
    shadow.innerHTML =
      "<style>" + CSS + "</style>" +
      '<div class="bar" role="navigation" aria-label="App ribbon">' +
        '<div class="meta">' +
          '<span class="led-wrap">' +
            '<span class="leds" role="group" aria-label="Git status" aria-describedby="led-tip">' +
              '<button class="led-btn" type="button" data-led="repo" aria-label="Repository status"><span class="led off" data-led-dot="repo" aria-hidden="true"></span></button>' +
              '<button class="led-btn" type="button" data-led="changes" aria-label="Changes status"><span class="led off" data-led-dot="changes" aria-hidden="true"></span></button>' +
              '<button class="led-btn" type="button" data-led="remote" aria-label="Remote status"><span class="led off" data-led-dot="remote" aria-hidden="true"></span></button>' +
            "</span>" +
            '<span class="led-tip" id="led-tip" role="tooltip" aria-hidden="true">' +
              '<span class="led-tip-row"><span class="led off" data-tip-led="repo" aria-hidden="true"></span><span data-tip-text="repo"></span></span>' +
              '<span class="led-tip-row"><span class="led off" data-tip-led="changes" aria-hidden="true"></span><span data-tip-text="changes"></span></span>' +
              '<span class="led-tip-row"><span class="led off" data-tip-led="remote" aria-hidden="true"></span><span data-tip-text="remote"></span></span>' +
            "</span>" +
          "</span>" +
          '<span class="count"></span>' +
        "</div>" +
        '<div class="title-wrap">' +
          '<button class="star-btn title-star" type="button" aria-pressed="false" aria-label="Add to favorites" title="Add to favorites">☆</button>' +
          '<button class="title" type="button" aria-haspopup="dialog" aria-expanded="false" title="Show all apps">' +
            '<span class="title-text"></span>' +
            '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>' +
          "</button>" +
        "</div>" +
        '<div class="actions">' +
          '<button class="btn" type="button" data-act="prev" aria-label="Previous app" title="Previous app — [">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>' +
            '<span class="label">Back</span>' +
          "</button>" +
          '<button class="btn" type="button" data-act="next" aria-label="Next app" title="Next app — ]">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>' +
            '<span class="label">Next</span>' +
          "</button>" +
          '<button class="btn" type="button" data-act="contents" aria-label="Show contents" aria-pressed="false" title="Show contents — C">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>' +
            '<span class="label">Contents</span>' +
          "</button>" +
          '<button class="btn" type="button" data-act="drift" aria-label="Drift to another app" title="Drift to another app — R">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 4l3 3-3 3"/><path d="M18 20l3-3-3-3"/><path d="M3 7h3c2 0 3.5 1 4.5 2.5l3 5C14.5 16 16 17 18 17h3"/><path d="M3 17h3c2 0 3.5-1 4.5-2.5l3-5C14.5 8 16 7 18 7h3"/></svg>' +
            '<span class="label">Drift</span>' +
          "</button>" +
          '<button class="btn" type="button" data-act="reload" aria-label="Reload app" title="Reload app — Shift+R">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>' +
          "</button>" +
          '<span class="sep" aria-hidden="true"></span>' +
          '<button class="btn" type="button" data-act="hide" aria-label="Hide ribbon" title="Hide ribbon — H">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6L6 18"/><path d="M6 6l12 12"/></svg>' +
          "</button>" +
        "</div>" +
        '<div class="menu" hidden role="dialog" aria-label="All apps">' +
          '<div class="menu-top">' +
            '<div class="menu-current">' +
              '<span class="menu-current-label">Current app</span>' +
              '<span class="menu-current-title"></span>' +
              '<span class="menu-current-meta"></span>' +
            "</div>" +
            '<button class="star-btn" type="button" aria-pressed="false" aria-label="Add to favorites" title="Add to favorites">☆</button>' +
          "</div>" +
          '<div class="menu-current-tools">' +
            '<button class="tool-btn" type="button" data-tool="keep" aria-pressed="false">Keep</button>' +
            '<button class="tool-btn" type="button" data-tool="park" aria-pressed="false">Park</button>' +
            '<span class="menu-current-hint">drift deals from the active channel</span>' +
          "</div>" +
          '<div class="menu-channels" role="group" aria-label="Channels"></div>' +
          '<div class="menu-search">' +
            '<input class="menu-input" type="search" placeholder="Search apps…" aria-label="Search apps" autocomplete="off" spellcheck="false">' +
          "</div>" +
          '<div class="menu-scroll">' +
            '<div class="menu-section" data-section="favorites" hidden>' +
              '<div class="menu-heading">Favorites</div>' +
              '<div class="menu-list" data-list="favorites"></div>' +
            "</div>" +
            '<div class="menu-section" data-section="all">' +
              '<div class="menu-heading">All apps</div>' +
              '<div class="menu-list" data-list="all"></div>' +
            "</div>" +
            '<div class="menu-empty" hidden>No apps match.</div>' +
          "</div>" +
        "</div>" +
      "</div>" +
      '<div class="card-overlay" hidden>' +
        '<button class="card-close" type="button" aria-label="Close contents" title="Close contents — Esc">✕ Close</button>' +
        '<iframe class="card-frame" title="Project contents"></iframe>' +
      "</div>" +
      '<button class="peek" type="button" aria-label="Show ribbon" title="Show ribbon — H">' +
        '<span aria-hidden="true">▤</span><span class="peek-label">ribbon</span>' +
      "</button>" +
      '<div class="git-overlay" hidden>' +
        '<div class="git-dialog" role="dialog" aria-modal="true" aria-labelledby="git-title">' +
          '<div class="git-head">' +
            '<div class="git-heading">' +
              '<div class="git-kicker">Git</div>' +
              '<div class="git-title" id="git-title"></div>' +
            "</div>" +
            '<button class="git-close" type="button" aria-label="Close">✕</button>' +
          "</div>" +
          '<div class="git-body">' +
            '<div class="git-summary"></div>' +
            '<div class="git-files" hidden></div>' +
            '<div class="git-warnings" hidden></div>' +
            '<label class="git-field git-message-field" hidden>' +
              '<span class="git-label">Commit message</span>' +
              '<input class="git-input git-message" type="text" maxlength="2000" autocomplete="off">' +
            "</label>" +
            '<label class="git-field git-name-field" hidden>' +
              '<span class="git-label">GitHub repo name</span>' +
              '<input class="git-input git-name" type="text" maxlength="100" autocomplete="off" spellcheck="false">' +
            "</label>" +
            '<div class="git-field git-visibility-field" hidden>' +
              '<span class="git-label">Visibility</span>' +
              '<div class="git-radios">' +
                '<label class="git-radio"><input type="radio" name="git-visibility" value="private" checked> Private</label>' +
                '<label class="git-radio"><input type="radio" name="git-visibility" value="public"> Public</label>' +
              "</div>" +
            "</div>" +
            '<label class="git-field git-description-field" hidden>' +
              '<span class="git-label">Description (optional)</span>' +
              '<input class="git-input git-description" type="text" maxlength="350" autocomplete="off" placeholder="What is this app?">' +
            "</label>" +
            '<label class="git-field git-readme-field" hidden>' +
              '<span class="git-label">README.md</span>' +
              '<textarea class="git-input git-textarea git-readme" rows="6" maxlength="20000" spellcheck="false" placeholder="Write a short README…"></textarea>' +
              '<span class="git-hint">No README yet. Ribbon will write this to README.md, commit it, and push it before publishing.</span>' +
            "</label>" +
            '<label class="git-check git-pages-field" hidden>' +
              '<input type="checkbox" class="git-pages">' +
              "<span>Publish with GitHub Pages and set it as the repo homepage</span>" +
            "</label>" +
            '<label class="git-check git-ignore-field" hidden>' +
              '<input type="checkbox" class="git-ignore" checked>' +
              "<span>Add a .gitignore for node_modules, .venv, dist…</span>" +
            "</label>" +
            '<div class="git-note" hidden></div>' +
            '<pre class="git-output" hidden></pre>' +
          "</div>" +
          '<div class="git-actions">' +
            '<span class="git-status"></span>' +
            '<button class="btn git-cancel" type="button">Close</button>' +
            '<button class="btn git-primary" type="button" hidden></button>' +
          "</div>" +
        "</div>" +
      "</div>" +
      '<div class="delete-overlay" hidden>' +
        '<div class="delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-warning">' +
          '<div class="delete-head">' +
            '<div class="delete-heading">' +
              '<div class="delete-kicker">Delete folder</div>' +
              '<div class="delete-title" id="delete-title"></div>' +
            "</div>" +
            '<button class="git-close delete-close" type="button" aria-label="Close">✕</button>' +
          "</div>" +
          '<div class="delete-body">' +
            '<p class="delete-warn" id="delete-warning">This removes the folder and everything inside it. It cannot be undone.</p>' +
            '<div class="delete-path"></div>' +
            "<div>" +
              '<div class="delete-command-label">Command</div>' +
              '<pre class="delete-command"></pre>' +
            "</div>" +
            '<div class="delete-note">Ribbon will run exactly this command, then remove the folder from the list.</div>' +
            '<pre class="delete-command delete-output" hidden></pre>' +
          "</div>" +
          '<div class="delete-actions">' +
            '<span class="delete-status" role="status" aria-live="polite"></span>' +
            '<button class="btn delete-cancel" type="button">Cancel</button>' +
            '<button class="btn delete-primary" type="button" disabled>Delete folder</button>' +
          "</div>" +
        "</div>" +
      "</div>"

    const bar = shadow.querySelector(".bar")
    const countEl = shadow.querySelector(".count")
    const titleButton = shadow.querySelector(".title")
    const titleText = shadow.querySelector(".title-text")
    const peekEl = shadow.querySelector(".peek")
    const ledRepo = shadow.querySelector('[data-led-dot="repo"]')
    const ledChanges = shadow.querySelector('[data-led-dot="changes"]')
    const ledRemote = shadow.querySelector('[data-led-dot="remote"]')
    const ledsWrap = shadow.querySelector(".leds")
    const ledButtons = shadow.querySelectorAll(".led-btn")
    const ledWrap = ledsWrap.parentNode
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
    const keepButton = shadow.querySelector('[data-tool="keep"]')
    const parkButton = shadow.querySelector('[data-tool="park"]')
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
      const pageTitle = (document.title || "").trim()
      return {
        index: found,
        title: exact && apps[found]
          ? apps[found].title
          : pageTitle || (apps[found] && apps[found].title) || "Untitled"
      }
    }

    const favorites = readFavorites()
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
      for (let i = 0; i < apps.length; i += 1) known[appKey(apps[i])] = true
      deck = (storedDeck.order || []).filter(function (key) {
        return known[key]
      })
      deckCursor = Number(storedDeck.cursor) || 0
      if (deckCursor >= deck.length) deckCursor = 0
    }
    let menuOpen = false
    let gitDetail = null
    let gitAction = null
    let gitBusy = false
    let gitBlocked = false
    let gitReturnFocus = null
    let cardOpen = false
    let cardSwitch = 0

    function applyApps() {
      const current = locate()
      index = current.index
      appIndex = {}
      for (let i = 0; i < apps.length; i += 1) {
        appIndex[appKey(apps[i])] = apps[i]
      }
      titleText.textContent = current.title
      titleButton.title = "Show all apps"
      menuCurrentTitle.textContent = current.title
      countEl.textContent = (index >= 0 ? pad(index + 1, apps.length) : "—") +
        " / " + pad(apps.length, apps.length)
      setGit(apps[index] && apps[index].git)
      updateCurrentStar()
      updateCurrentMeta()
      for (let k = 0; k < buttons.length; k += 1) {
        const act = buttons[k].getAttribute("data-act")
        if (act !== "hide") buttons[k].disabled = apps.length < 2
      }
      contentsButton.disabled = !apps[index] || apps[index].kind !== "page"
      if (contentsButton.disabled) setCardOpen(false)
      if (menuOpen) {
        renderChannels()
        renderMenu(searchInput.value)
      }
      if (window.__ribbon) window.__ribbon.apps = apps
    }

    applyApps()
    let manualHidden = readHidden()
    let autoHidden = false
    let topOffset = false
    let savedPaddingTop = null
    const lastTargets = new Map()
    let tipPinned = false
    let tipTimer = 0
    const hoverCapable = window.matchMedia("(hover: hover)").matches

    // Reserve a strip at the top of the page for the bar, so the app's own
    // header is not covered while you are at the very top. Scrolling down
    // still turns the bar into an overlay that slides away.
    function setTopOffset(on, compensate) {
      const body = document.body
      if (!body || topOffset === on) return
      const before = compensate ? scrollY() : 0

      if (on) {
        if (!savedPaddingTop) {
          savedPaddingTop = {
            value: body.style.getPropertyValue("padding-top"),
            priority: body.style.getPropertyPriority("padding-top")
          }
        }
        const base = parseFloat(window.getComputedStyle(body).paddingTop) || 0
        body.style.setProperty("padding-top", (base + BAR_HEIGHT) + "px", "important")
      } else if (savedPaddingTop) {
        if (savedPaddingTop.value) {
          body.style.setProperty(
            "padding-top",
            savedPaddingTop.value,
            savedPaddingTop.priority
          )
        } else {
          body.style.removeProperty("padding-top")
        }
      }

      topOffset = on
      if (!compensate || before === 0) return

      // Keep the page still when the strip is added or removed by hand.
      const after = on ? before + BAR_HEIGHT : Math.max(0, before - BAR_HEIGHT)
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
        closeTip()
        closeMenu(false)
      }
      bar.classList.toggle("is-gone", gone)
      if (gone) bar.setAttribute("inert", "")
      else bar.removeAttribute("inert")
      peekEl.classList.toggle("is-shown", manualHidden)
      peekEl.tabIndex = manualHidden ? 0 : -1
    }

    function setManual(hidden) {
      manualHidden = hidden
      if (hidden) autoHidden = false
      else lastTargets.clear()
      setTopOffset(!hidden, true)
      try {
        sessionStorage.setItem(STORAGE_KEY, hidden ? "1" : "0")
      } catch (_) { /* storage may be unavailable */ }
      applyState()
    }

    function go(direction) {
      if (apps.length < 2) return
      let target
      if (index < 0) {
        target = direction > 0 ? 0 : apps.length - 1
      } else {
        target = (index + direction + apps.length) % apps.length
        if (target === index) return
      }
      location.assign(apps[target].url)
    }

    function drift() {
      if (apps.length < 2) return
      if (!ensureDeck()) return
      const current = appKey(currentApp())
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
      if (app) location.assign(app.url)
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
          items.push({ key: appKey(apps[i]), weight: weight })
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
      const key = appKey(app)
      const entry = signals[key] || {}
      if (isParked(entry)) return 0
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
      if (entry.keep) weight += 2.2
      if (favorites.has(key)) weight += 1.2
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
      const entry = signals[appKey(app)] || {}
      if (!entry.last_opened) return true
      const opened = Date.parse(entry.last_opened)
      return !opened || Date.now() - opened > 30 * 86400000
    }

    function isParked(entry) {
      return !!(
        entry &&
        entry.parked_until &&
        Date.parse(entry.parked_until) > Date.now()
      )
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
      closeMenu(false)
      location.reload()
    }

    function appKey(app) {
      return app ? app.dir || app.path || app.url || "" : ""
    }

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
      const app = currentApp()
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

    function updateCurrentStar() {
      const app = currentApp()
      const favorite = isFavorite(app)
      const name = app ? app.title || "this app" : "this app"
      const label = (favorite ? "Remove " : "Add ") +
        name + (favorite ? " from favorites" : " to favorites")
      for (let i = 0; i < starButtons.length; i += 1) {
        const button = starButtons[i]
        button.disabled = !app
        button.setAttribute("aria-pressed", favorite ? "true" : "false")
        button.textContent = favorite ? "★" : "☆"
        button.title = label
        button.setAttribute("aria-label", label)
      }
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
      menuCurrentMeta.textContent = bits.join(" · ")
      const keep = !!entry.keep
      const park = isParked(entry)
      keepButton.disabled = !app
      parkButton.disabled = !app
      keepButton.setAttribute("aria-pressed", keep ? "true" : "false")
      parkButton.setAttribute("aria-pressed", park ? "true" : "false")
      keepButton.textContent = keep ? "Kept" : "Keep"
      parkButton.textContent = park ? "Parked" : "Park"
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

    function signal(name, value) {
      const app = currentApp()
      if (!app) return
      const key = appKey(app)
      const entry = Object.assign({}, signals[key] || {})
      const now = new Date()
      if (name === "open") {
        entry.opens = (Number(entry.opens) || 0) + 1
        entry.last_opened = now.toISOString()
      } else if (name === "keep") {
        entry.keep = !!value
        if (entry.keep) entry.parked_until = null
      } else if (name === "park") {
        entry.parked_until = value
          ? new Date(now.getTime() + 14 * 86400000).toISOString()
          : null
      } else if (name === "note") {
        if (value) entry.note = String(value).slice(0, 500)
        else delete entry.note
      }
      entry.updated = now.toISOString()
      signals[key] = entry
      if (name === "keep" || name === "park") deck = []
      updateCurrentMeta()
      if (menuOpen) {
        renderChannels()
        renderMenu(searchInput.value)
      }
      if (!ribbonToken) return
      fetch(new URL("signal", scriptBase).href, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Ribbon-Token": ribbonToken
        },
        body: JSON.stringify({ path: key, signal: name, value: value })
      })
        .then(function (response) {
          return response.json()
        })
        .then(function (data) {
          if (!data || !data.ok || !data.state || !data.state.assets) return
          mergeSignals(data.state.assets)
          if (name === "keep" || name === "park") deck = []
          updateCurrentMeta()
          if (menuOpen) {
            renderChannels()
            renderMenu(searchInput.value)
          }
        })
        .catch(function () { /* the local signal stands */ })
    }

    const LED_WORK = { ok: 0, warn: 1, bad: 2, off: 3 }

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

    function menuLights(git) {
      const lights = gitLights(git)
      const classes = [ lights.repoClass, lights.changesClass, lights.remoteClass ]
      const wrap = document.createElement("span")
      wrap.className = "menu-leds"
      wrap.setAttribute("role", "img")
      for (let i = 0; i < classes.length; i += 1) {
        const dot = document.createElement("span")
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
      const row = document.createElement("div")
      row.className = "menu-row" + (appIndex === index ? " is-current" : "")

      const open = document.createElement("button")
      open.type = "button"
      open.className = "menu-app"
      open.setAttribute("data-app", String(appIndex))
      if (appIndex === index) open.setAttribute("aria-current", "true")

      const title = document.createElement("span")
      title.className = "menu-app-title"
      if (app.icon) {
        const glyph = document.createElement("span")
        glyph.className = "menu-app-glyph"
        glyph.textContent = app.icon
        glyph.title = app.type || "Project"
        glyph.setAttribute("aria-hidden", "true")
        if (app.color) glyph.style.color = app.color
        title.appendChild(glyph)
      }
      title.appendChild(document.createTextNode(app.title || "Untitled"))
      const entry = signals[appKey(app)] || {}
      if (entry.keep || isParked(entry)) {
        const flag = document.createElement("span")
        flag.className = "menu-app-flag"
        flag.textContent = isParked(entry) ? "parked" : "kept"
        title.appendChild(flag)
      }

      const path = app.path || app.dir || ""
      const dir = document.createElement("span")
      dir.className = "menu-app-dir"
      dir.textContent = path && path !== "." ? "/" + path : "/"

      open.appendChild(title)
      open.appendChild(dir)

      const star = document.createElement("button")
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
        const remove = document.createElement("button")
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

    function matchesQuery(app, query) {
      if (!query) return true
      const haystack = String(app.title || "").toLowerCase() +
        " " + String(app.path || app.dir || "").toLowerCase() +
        " " + String(app.type || "").toLowerCase()
      return haystack.indexOf(query) !== -1
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

    function renderMenu(query) {
      const needle = (query || "").trim().toLowerCase()
      menuFavList.textContent = ""
      menuAllList.textContent = ""
      let favoriteCount = 0
      let otherCount = 0
      const rows = []

      apps.forEach(function (app, appIndex) {
        if (!channelMatches(app, activeChannel)) return
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
          menuFavList.appendChild(favoriteRow(app, appIndex))
          favoriteCount += 1
        } else {
          menuAllList.appendChild(favoriteRow(app, appIndex))
          otherCount += 1
        }
      })

      menuFavSection.hidden = favoriteCount === 0
      menuAllSection.hidden = otherCount === 0
      menuEmpty.hidden = favoriteCount + otherCount > 0
      menuEmpty.textContent = activeChannel === "all"
        ? "No apps match."
        : "Nothing in this channel."
      if (activeChannel === "all") {
        menuAllHeading.textContent = favoriteCount ? "Other apps" : "All apps"
      } else {
        menuAllHeading.textContent = channelLabel(activeChannel)
      }
    }

    function openMenu() {
      if (!apps.length) return
      if (menuOpen) {
        searchInput.focus()
        searchInput.select()
        return
      }
      menuOpen = true
      menuEl.hidden = false
      titleButton.setAttribute("aria-expanded", "true")
      searchInput.value = ""
      renderChannels()
      renderMenu("")
      updateCurrentStar()
      updateCurrentMeta()
      requestAnimationFrame(function () {
        searchInput.focus()
        searchInput.select()
      })
    }

    function closeMenu(returnFocus) {
      if (!menuOpen) return
      menuOpen = false
      menuEl.hidden = true
      titleButton.setAttribute("aria-expanded", "false")
      if (returnFocus) titleButton.focus()
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
      renderMenu(searchInput.value)
      updateCurrentStar()
      if (focusStar) {
        const stars = menuEl.querySelectorAll("[data-star]")
        for (let i = 0; i < stars.length; i += 1) {
          if (stars[i].getAttribute("data-star") === key) {
            stars[i].focus()
            break
          }
        }
      }
    }

    function removeDeletedApp(app) {
      const key = appKey(app)
      apps = apps.filter(function (item) {
        return appKey(item) !== key
      })
      favorites.delete(key)
      saveFavorites()
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
      deleteTitle.textContent = app.title || appKey(app)
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
      if (reopen && apps.length) openMenu()
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
      closeMenu(false)
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
      const key = appKey(app)
      const dir = app.path || app.dir || ""
      const wasCurrent = index >= 0 && appKey(apps[index]) === key
      const fallback = apps.filter(function (item) {
        return appKey(item) !== key
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
            location.assign(fallback ? fallback.url : "/")
          } else {
            openMenu()
          }
        })
        .catch(function (error) {
          setDeleteBusy(false)
          showDeleteError({ error: error.message || "The request failed." })
        })
    }

    function defaultRepoName() {
      const app = currentApp()
      const path = app ? app.path || app.dir || "" : ""
      let name = path.split("/").pop() || (app && app.title) || "app"
      name = name.replace(/^\d{4}-\d{2}-\d{2}-/, "")
      name = name.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|[-.]+$/g, "")
      return (name || "app").slice(0, 100)
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

    function summaryRow(label, value) {
      const row = document.createElement("div")
      row.className = "git-summary-row"
      const labelEl = document.createElement("span")
      labelEl.className = "git-summary-label"
      labelEl.textContent = label
      const valueEl = document.createElement("span")
      valueEl.className = "git-summary-value"
      valueEl.textContent = value
      valueEl.title = value
      row.appendChild(labelEl)
      row.appendChild(valueEl)
      gitSummary.appendChild(row)
    }

    function renderGitUnavailable(message) {
      gitDetail = null
      gitAction = null
      gitBlocked = false
      gitTitle.textContent = "Git unavailable"
      gitSummary.textContent = ""
      summaryRow("Status", message)
      gitFiles.hidden = true
      gitWarnings.hidden = true
      gitMessageField.hidden = true
      gitNameField.hidden = true
      gitVisibilityField.hidden = true
      gitDescriptionField.hidden = true
      gitReadmeField.hidden = true
      gitPagesField.hidden = true
      gitIgnoreField.hidden = true
      gitNote.hidden = true
      gitOutput.hidden = true
      gitStatus.className = "git-status"
      gitStatus.textContent = ""
      gitPrimary.hidden = true
      gitCancel.textContent = "Close"
      gitCancel.focus()
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
      gitTitle.textContent = titles[gitAction] || "Git status"

      gitSummary.textContent = ""
      summaryRow("Folder", detail.root || (app && (app.path || app.dir)) || "—")
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
      gitFiles.textContent = ""
      gitFiles.hidden = !((gitAction === "commit" || gitAction === "init") && files.length)
      if (!gitFiles.hidden) {
        files.slice(0, 12).forEach(function (item) {
          const row = document.createElement("div")
          row.className = "git-file"
          const code = document.createElement("span")
          code.className = "git-file-code"
          code.textContent = item.code.trim() || "?"
          const path = document.createElement("span")
          path.className = "git-file-path"
          path.textContent = item.path
          path.title = item.path
          row.appendChild(code)
          row.appendChild(path)
          gitFiles.appendChild(row)
        })
        if (files.length > 12) {
          const more = document.createElement("div")
          more.className = "git-file-more"
          more.textContent = "+" + (files.length - 12) + " more"
          gitFiles.appendChild(more)
        }
      }

      const warnings = (detail.warnings || []).filter(function (warning) {
        if (gitAction !== "init" || detail.has_gitignore) return true
        return !(
          warning.indexOf("No .gitignore") === 0 ||
          warning.indexOf("is not gitignored") >= 0
        )
      })
      gitWarnings.textContent = ""
      gitWarnings.hidden = warnings.length === 0
      warnings.forEach(function (warning) {
        const row = document.createElement("div")
        row.className = "git-warning"
        row.textContent = warning
        gitWarnings.appendChild(row)
      })

      const canWrite = !!gitToken
      gitMessageField.hidden = !(gitAction === "commit" || gitAction === "init")
      if (!gitMessageField.hidden) {
        gitMessage.value = gitAction === "init"
          ? "Initial commit"
          : "Update " + ((app && app.title) || detail.branch || "app")
      }
      gitNameField.hidden = gitAction !== "remote"
      if (!gitNameField.hidden) gitName.value = defaultRepoName()
      gitVisibilityField.hidden = gitAction !== "remote"
      if (!gitVisibilityField.hidden) {
        for (let i = 0; i < gitVisibilityInputs.length; i += 1) {
          gitVisibilityInputs[i].checked = gitVisibilityInputs[i].value === "private"
        }
      }
      gitDescriptionField.hidden = gitAction !== "remote"
      if (!gitDescriptionField.hidden) gitDescription.value = ""
      const readmeMissing = !(detail.readme && detail.readme.exists)
      gitReadmeField.hidden = !(
        (gitAction === "remote" || gitAction === "pages") && readmeMissing
      )
      if (!gitReadmeField.hidden) {
        gitReadme.value = "# " + ((app && app.title) || "App") + "\n\n"
      }
      gitPagesField.hidden = gitAction !== "remote"
      if (!gitPagesField.hidden) gitPages.checked = false
      gitIgnoreField.hidden = gitAction !== "init" || !!detail.has_gitignore
      if (!gitIgnoreField.hidden) gitIgnore.checked = true

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
      gitNote.textContent = notes.join("\n\n")
      gitNote.hidden = notes.length === 0

      gitOutput.hidden = true
      gitOutput.textContent = ""
      gitStatus.className = "git-status" + (success ? " is-good" : "")
      gitStatus.textContent = success || ""

      gitBlocked =
        !canWrite ||
        detail.identity_ok === false && (gitAction === "commit" || gitAction === "init") ||
        (gitAction === "remote" || gitAction === "pages") && detail.gh === false ||
        gitAction === "pages" && !!(detail.pages && detail.pages.problem) ||
        gitAction === "pages-entry" && !(detail.pages && detail.pages.entry)
      gitPrimary.textContent = labels[gitAction] || ""
      gitPrimary.hidden = !labels[gitAction]
      gitPrimary.disabled = gitBlocked
      gitCancel.textContent = gitAction === "info" ? "Close" : "Cancel"
      gitCancel.disabled = false
      gitClose.disabled = false

      if (!gitReadmeField.hidden) gitReadme.focus()
      else if (gitAction === "commit" || gitAction === "init") gitMessage.focus()
      else if (gitAction === "remote") gitName.focus()
      else if (gitAction === "push" || gitAction === "pages" || gitAction === "pages-entry") gitPrimary.focus()
      else gitCancel.focus()
    }

    function openGitPanel(focus) {
      const app = currentApp()
      if (!app || !gitOverlay.hidden) return
      closeMenu(false)
      closeTip()
      gitReturnFocus = document.activeElement
      gitOverlay.hidden = false
      gitBusy = false
      gitStatus.className = "git-status"
      gitStatus.textContent = ""
      gitOutput.hidden = true
      gitOutput.textContent = ""
      gitTitle.textContent = "Checking Git…"
      gitSummary.textContent = ""
      gitFiles.hidden = true
      gitWarnings.hidden = true
      gitNote.hidden = true
      gitMessageField.hidden = true
      gitNameField.hidden = true
      gitVisibilityField.hidden = true
      gitDescriptionField.hidden = true
      gitReadmeField.hidden = true
      gitPagesField.hidden = true
      gitIgnoreField.hidden = true
      gitPrimary.hidden = true

      if (location.protocol !== "http:" && location.protocol !== "https:") {
        renderGitUnavailable("Start the ribbon server to use Git actions.")
        return
      }

      const dir = app.path || app.dir || ""
      fetch("/__ribbon/git.json?dir=" + encodeURIComponent(dir), { cache: "no-store" })
        .then(function (response) {
          if (!response.ok) throw new Error("HTTP " + response.status)
          return response.json()
        })
        .then(function (detail) {
          setGit(detail)
          if (currentApp()) currentApp().git = detail
          renderGitPanel(detail, focus, "")
        })
        .catch(function (error) {
          renderGitUnavailable("Could not read Git status: " + (error.message || error))
        })
    }

    function closeGitPanel() {
      if (gitBusy) return
      gitOverlay.hidden = true
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
      gitPrimary.disabled = busy || gitBlocked
      gitCancel.disabled = busy
      gitClose.disabled = busy
      if (busy) {
        gitPrimary.textContent = "Working…"
      } else if (gitAction) {
        const labels = {
          init: "Create repo + commit",
          commit: "Commit changes",
          push: "Push commits",
          remote: "Create repo + push",
          pages: "Publish to GitHub Pages",
          "pages-entry": "Create index.html"
        }
        gitPrimary.textContent = labels[gitAction] || "Continue"
      }
    }

    function showGitError(data) {
      const error = (data && (data.error || data.message)) || "The Git action failed."
      const output = (data && data.output) || ""
      gitStatus.className = "git-status is-bad"
      gitStatus.textContent = error.split("\n")[0].slice(0, 140)
      gitOutput.textContent = [ error, output ].filter(Boolean).join("\n\n")
      gitOutput.hidden = !gitOutput.textContent
    }

    function submitGitAction() {
      if (gitBusy || !gitAction) return
      const app = currentApp()
      if (!app) return

      const payload = { action: gitAction, dir: app.path || app.dir || "" }
      if (gitAction === "init" || gitAction === "commit") {
        payload.message = gitMessage.value.trim()
        if (!payload.message) {
          gitMessage.focus()
          return
        }
      }
      if (gitAction === "init") payload.gitignore = gitIgnore.checked
      if (gitAction === "remote") {
        payload.name = gitName.value.trim()
        if (!payload.name) {
          gitName.focus()
          return
        }
        const checked = shadow.querySelector('input[name="git-visibility"]:checked')
        payload.visibility = checked ? checked.value : "private"
        payload.description = gitDescription.value.trim()
        payload.pages = gitPages.checked
      }
      if (!gitReadmeField.hidden) payload.readme = gitReadme.value

      setGitBusy(true)
      gitStatus.className = "git-status"
      gitStatus.textContent = "Working…"
      gitOutput.hidden = true
      gitOutput.textContent = ""

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
            if (currentApp()) currentApp().git = data.status
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

    function setGit(git) {
      const lights = gitLights(git)

      ledRepo.className = "led " + lights.repoClass
      ledChanges.className = "led " + lights.changesClass
      ledRemote.className = "led " + lights.remoteClass
      tipRepoDot.className = "led " + lights.repoClass
      tipChangesDot.className = "led " + lights.changesClass
      tipRemoteDot.className = "led " + lights.remoteClass

      const repoText = repoTip(git)
      const changesText = changesTip(git, lights.dirty, lights.count)
      const remoteText = remoteTip(git, lights.hasRemote)
      tipRepoText.textContent = repoText
      tipChangesText.textContent = changesText
      tipRemoteText.textContent = remoteText
      ledsWrap.setAttribute("aria-label", repoText + ". " + changesText + ". " + remoteText)

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

    function setLedLabel(name, text, hint) {
      for (let i = 0; i < ledButtons.length; i += 1) {
        if (ledButtons[i].getAttribute("data-led") === name) {
          ledButtons[i].setAttribute("aria-label", text + ". " + hint)
          ledButtons[i].title = text + " — " + hint
          return
        }
      }
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

    function openTip(pin) {
      if (pin) tipPinned = true
      ledTip.classList.add("is-open")
      ledTip.setAttribute("aria-hidden", "false")
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
      ledTip.classList.remove("is-open")
      ledTip.setAttribute("aria-hidden", "true")
      if (tipTimer) {
        clearTimeout(tipTimer)
        tipTimer = 0
      }
    }

    function closeTipIfUnpinned() {
      if (!tipPinned) closeTip()
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

    titleButton.addEventListener("click", toggleMenu)
    starTitle.addEventListener("click", function () {
      const app = currentApp()
      if (app) toggleFavorite(app, false)
      starTitle.focus()
    })
    starCurrent.addEventListener("click", function () {
      const app = currentApp()
      if (app) toggleFavorite(app, false)
      starCurrent.focus()
    })
    keepButton.addEventListener("click", function () {
      const entry = signals[appKey(currentApp())] || {}
      signal("keep", !entry.keep)
    })
    parkButton.addEventListener("click", function () {
      const entry = signals[appKey(currentApp())] || {}
      signal("park", !isParked(entry))
    })
    menuChannels.addEventListener("click", function (event) {
      const chip = event.target && event.target.closest
        ? event.target.closest("[data-channel]")
        : null
      if (!chip) return
      activeChannel = chip.getAttribute("data-channel") || "all"
      saveChannel()
      deck = []
      deckChannel = activeChannel
      deckCursor = 0
      renderChannels()
      renderMenu(searchInput.value)
      searchInput.focus()
    })
    searchInput.addEventListener("input", function () {
      renderMenu(searchInput.value)
    })
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault()
        closeMenu(true)
        return
      }
      if (event.key === "Enter") {
        const first = menuEl.querySelector(".menu-app")
        if (first) {
          event.preventDefault()
          location.assign(apps[Number(first.getAttribute("data-app"))].url)
        }
        return
      }
      if (event.key === "ArrowDown") {
        const first = menuEl.querySelector(".menu-app")
        if (first) {
          event.preventDefault()
          first.focus()
        }
      }
    })
    menuEl.addEventListener("click", function (event) {
      const remove = event.target && event.target.closest
        ? event.target.closest(".row-delete")
        : null
      if (remove) {
        const key = remove.getAttribute("data-delete")
        for (let i = 0; i < apps.length; i += 1) {
          if (appKey(apps[i]) === key) {
            openDeletePanel(apps[i])
            break
          }
        }
        return
      }

      const star = event.target && event.target.closest
        ? event.target.closest(".row-star")
        : null
      if (star) {
        for (let i = 0; i < apps.length; i += 1) {
          if (appKey(apps[i]) === star.getAttribute("data-star")) {
            toggleFavorite(apps[i], true)
            break
          }
        }
        return
      }

      const row = event.target && event.target.closest
        ? event.target.closest(".menu-app")
        : null
      if (row) {
        location.assign(apps[Number(row.getAttribute("data-app"))].url)
      }
    })
    document.addEventListener("pointerdown", function (event) {
      if (!menuOpen) return
      const path = event.composedPath ? event.composedPath() : []
      if (path.indexOf(menuEl) !== -1 || path.indexOf(titleButton) !== -1) return
      closeMenu(false)
    }, true)

    ledsWrap.addEventListener("click", function (event) {
      const button = event.target && event.target.closest
        ? event.target.closest(".led-btn")
        : null
      if (!button) return
      event.stopPropagation()
      openGitPanel(button.getAttribute("data-led"))
    })
    ledsWrap.addEventListener("pointerenter", function () {
      if (hoverCapable) openTip(false)
    })
    ledsWrap.addEventListener("pointerleave", closeTipIfUnpinned)
    for (let b = 0; b < ledButtons.length; b += 1) {
      ledButtons[b].addEventListener("focus", function () {
        openTip(false)
      })
      ledButtons[b].addEventListener("blur", closeTipIfUnpinned)
    }

    gitCancel.addEventListener("click", closeGitPanel)
    gitClose.addEventListener("click", closeGitPanel)
    gitPrimary.addEventListener("click", submitGitAction)
    gitOverlay.addEventListener("pointerdown", function (event) {
      if (event.target === gitOverlay) closeGitPanel()
    })
    gitOverlay.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault()
        closeGitPanel()
      }
    })

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
      if (event.key === "Escape") {
        event.preventDefault()
        closeDeletePanel(true)
      }
    })
    document.addEventListener("pointerdown", function (event) {
      if (!ledTip.classList.contains("is-open")) return
      const path = event.composedPath ? event.composedPath() : []
      if (path.indexOf(ledWrap) !== -1) return
      closeTip()
    }, true)

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
          closeGitPanel()
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
      if (key === "Escape" && menuOpen) {
        closeMenu(true)
        event.preventDefault()
        event.stopPropagation()
        return
      }
      if (key === "/") {
        openMenu()
        event.preventDefault()
        event.stopPropagation()
        return
      }
      if (menuOpen) return
      if (key === "Escape" && ledTip.classList.contains("is-open")) {
        closeTip()
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
      } else if (key === "k" || key === "K") {
        const entry = signals[appKey(currentApp())] || {}
        signal("keep", !entry.keep)
      } else if (key === "p" || key === "P") {
        const entry = signals[appKey(currentApp())] || {}
        signal("park", !isParked(entry))
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
      keep: function (on) {
        const entry = signals[appKey(currentApp())] || {}
        signal("keep", typeof on === "boolean" ? on : !entry.keep)
      },
      park: function (on) {
        const entry = signals[appKey(currentApp())] || {}
        signal("park", typeof on === "boolean" ? on : !isParked(entry))
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
        if (currentApp()) signal("open", true)
      }
    }

    setTopOffset(!manualHidden, false)
    applyState()
    document.documentElement.appendChild(host)
    if (!openedRecorded) {
      openedRecorded = true
      if (currentApp()) signal("open", true)
    }
    return update
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
      return new URL(app.url, location.href).pathname
    } catch (_) {
      return app.url
    }
  }

  function pad(number, total) {
    const width = String(total).length
    let value = String(number)
    while (value.length < width) value = "0" + value
    return value
  }

  function readHidden() {
    try {
      return sessionStorage.getItem(STORAGE_KEY) === "1"
    } catch (_) {
      return false
    }
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

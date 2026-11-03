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

  const STORAGE_KEY = "ribbon:hidden"
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
      .git-overlay { padding: 8px; }
      .git-dialog { max-height: calc(100vh - 16px); }
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

    fetch(manifestUrl, { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status)
        return response.json()
      })
      .then(function (data) {
        const apps = Array.isArray(data) ? data : data && data.apps
        if (Array.isArray(apps) && apps.length) mount(apps)
      })
      .catch(function () {
        /* No manifest (for example, opened from file://): stay quiet. */
      })
  }

  function mount(rawApps) {
    const apps = rawApps.filter(function (app) {
      return app && typeof app.url === "string" && app.url
    })
    if (!apps.length) return

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
          '<button class="btn" type="button" data-act="random" aria-label="Random app" title="Random app — R">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 4l3 3-3 3"/><path d="M18 20l3-3-3-3"/><path d="M3 7h3c2 0 3.5 1 4.5 2.5l3 5C14.5 16 16 17 18 17h3"/><path d="M3 17h3c2 0 3.5-1 4.5-2.5l3-5C14.5 8 16 7 18 7h3"/></svg>' +
            '<span class="label">Random</span>' +
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
            "</div>" +
            '<button class="star-btn" type="button" aria-pressed="false" aria-label="Add to favorites" title="Add to favorites">☆</button>' +
          "</div>" +
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

    const menuEl = shadow.querySelector(".menu")
    const menuCurrentTitle = shadow.querySelector(".menu-current-title")
    const starCurrent = shadow.querySelector(".star-btn")
    const searchInput = shadow.querySelector(".menu-input")
    const menuFavSection = shadow.querySelector('[data-section="favorites"]')
    const menuAllSection = shadow.querySelector('[data-section="all"]')
    const menuFavList = shadow.querySelector('[data-list="favorites"]')
    const menuAllList = shadow.querySelector('[data-list="all"]')
    const menuAllHeading = menuAllSection.querySelector(".menu-heading")
    const menuEmpty = shadow.querySelector(".menu-empty")

    const here = normalizePath(location.pathname)
    let index = -1
    for (let i = 0; i < apps.length; i += 1) {
      if (normalizePath(entryPath(apps[i])) === here) {
        index = i
        break
      }
    }
    const exact = index >= 0
    if (index < 0) {
      let bestLength = -1
      for (let j = 0; j < apps.length; j += 1) {
        const candidate = normalizePath(entryPath(apps[j]))
        if (here.indexOf(candidate) === 0 && candidate.length > bestLength) {
          bestLength = candidate.length
          index = j
        }
      }
    }

    const pageTitle = (document.title || "").trim()
    const currentTitle = exact && apps[index]
      ? apps[index].title
      : pageTitle || (apps[index] && apps[index].title) || "Untitled"

    const favorites = readFavorites()
    let menuOpen = false
    let gitDetail = null
    let gitAction = null
    let gitBusy = false
    let gitBlocked = false
    let gitReturnFocus = null

    titleText.textContent = currentTitle
    titleButton.title = "Show all apps"
    menuCurrentTitle.textContent = currentTitle
    countEl.textContent = (index >= 0 ? pad(index + 1, apps.length) : "—") + " / " + pad(apps.length, apps.length)
    setGit(apps[index] && apps[index].git)
    updateCurrentStar()

    if (apps.length < 2) {
      for (let k = 0; k < buttons.length; k += 1) {
        const act = buttons[k].getAttribute("data-act")
        if (act !== "hide") buttons[k].disabled = true
      }
    }

    let manualHidden = readHidden()
    let autoHidden = false
    const lastTargets = new Map()
    let tipPinned = false
    let tipTimer = 0
    const hoverCapable = window.matchMedia("(hover: hover)").matches

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

    function random() {
      if (apps.length < 2) return
      const choices = apps.length - (index >= 0 ? 1 : 0)
      let pick = Math.floor(Math.random() * choices)
      if (index >= 0 && pick >= index) pick += 1
      location.assign(apps[pick].url)
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

    function updateCurrentStar() {
      const app = currentApp()
      const favorite = isFavorite(app)
      const name = app ? app.title || "this app" : "this app"
      const label = (favorite ? "Remove " : "Add ") +
        name + (favorite ? " from favorites" : " to favorites")
      starCurrent.disabled = !app
      starCurrent.setAttribute("aria-pressed", favorite ? "true" : "false")
      starCurrent.textContent = favorite ? "★" : "☆"
      starCurrent.title = label
      starCurrent.setAttribute("aria-label", label)
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
      if (app.kind === "project" && app.icon) {
        const glyph = document.createElement("span")
        glyph.className = "menu-app-glyph"
        glyph.textContent = app.icon
        glyph.setAttribute("aria-hidden", "true")
        if (app.color) glyph.style.color = app.color
        title.appendChild(glyph)
      }
      title.appendChild(document.createTextNode(app.title || "Untitled"))

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
      return row
    }

    function matchesQuery(app, query) {
      if (!query) return true
      const haystack = String(app.title || "").toLowerCase() +
        " " + String(app.path || app.dir || "").toLowerCase() +
        " " + String(app.type || "").toLowerCase()
      return haystack.indexOf(query) !== -1
    }

    function renderMenu(query) {
      const needle = (query || "").trim().toLowerCase()
      menuFavList.textContent = ""
      menuAllList.textContent = ""
      let favoriteCount = 0
      let otherCount = 0
      const rows = []

      apps.forEach(function (app, appIndex) {
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
      menuAllHeading.textContent = favoriteCount ? "Other apps" : "All apps"
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
      renderMenu("")
      updateCurrentStar()
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
      if (gitAction === "pages" && detail.pages && !detail.pages.index) {
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
        return !(
          gitAction === "init" &&
          !detail.has_gitignore &&
          warning.indexOf("No .gitignore") === 0
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
        notes.push("This enables GitHub Pages for the current branch and sets the Pages address as the repo homepage.")
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
        gitAction === "pages-entry" && !(detail.pages && detail.pages.entry)
      gitPrimary.textContent = labels[gitAction] || ""
      gitPrimary.hidden = !labels[gitAction]
      gitPrimary.disabled = gitBlocked
      gitCancel.textContent = gitAction === "info" ? "Close" : "Cancel"
      gitCancel.disabled = false
      gitClose.disabled = false

      if (gitAction === "commit" || gitAction === "init") gitMessage.focus()
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
      else if (action === "random") random()
      else if (action === "reload") reloadApp()
      else if (action === "hide") setManual(true)
    })
    peekEl.addEventListener("click", function () {
      setManual(false)
    })

    titleButton.addEventListener("click", toggleMenu)
    starCurrent.addEventListener("click", function () {
      const app = currentApp()
      if (app) toggleFavorite(app, false)
      starCurrent.focus()
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
      if (!gitOverlay.hidden) {
        if (key === "Escape") {
          closeGitPanel()
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
      else if (key === "r" || key === "R") {
        if (event.shiftKey) reloadApp()
        else random()
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
      random: random,
      apps: apps
    }

    applyState()
    document.documentElement.appendChild(host)
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

  function scrollY() {
    return window.scrollY || window.pageYOffset || document.documentElement.scrollTop || 0
  }

  boot()
})()

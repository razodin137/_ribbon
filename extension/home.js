/* Ribbon — point the bar's home button at the new tab page.
 *
 * The bar is rendered by the server, which cannot know this extension's
 * address. The content script can, so it fills in the button's link and shows
 * it. A page with no bar is left alone.
 */
const host = document.querySelector("[data-ribbon-host]")
const root = host ? host.shadowRoot : null
const home = root ? root.querySelector("[data-home]") : null
const link = home ? home.querySelector("[data-home-link]") : null

if (link) {
  link.href = globalThis.chrome.runtime.getURL("newtab.html")
}
if (home) {
  home.hidden = false
}

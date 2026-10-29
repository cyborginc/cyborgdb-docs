// Forwards campaign attribution from docs.cyborg.co to the dashboard (cyborgdb.co).
// The dashboard lives on a different registrable domain, so cookies can't carry attribution across domains.
//
// Mintlify injects this file on every page (it sits next to docs.json). UTM
// parameters are captured from the URL on landing and on each client-side
// navigation, held in sessionStorage for the rest of the visit, and appended
// to any dashboard link at click time.
(function () {
  var UTM_KEYS = ['utm_campaign', 'utm_source', 'utm_medium', 'utm_content'];
  var STORAGE_KEY = 'cyborg_attribution';
  var DASHBOARD_HOST = 'cyborgdb.co';

  function capture(search) {
    var params;
    try {
      params = new URLSearchParams(search);
    } catch (e) {
      return;
    }
    var found = {};
    var hasAny = false;
    UTM_KEYS.forEach(function (key) {
      var value = params.get(key);
      if (value) {
        found[key] = value;
        hasAny = true;
      }
    });
    if (!hasAny) return;
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(found));
    } catch (e) {
      // Storage unavailable (private mode, blocked) — links just stay undecorated.
    }
  }

  function stored() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY)) || null;
    } catch (e) {
      return null;
    }
  }

  function decorate(anchor) {
    var saved = stored();
    if (!saved) return;
    var url;
    try {
      url = new URL(anchor.href);
    } catch (e) {
      return;
    }
    if (url.hostname !== DASHBOARD_HOST && !url.hostname.endsWith('.' + DASHBOARD_HOST)) return;
    UTM_KEYS.forEach(function (key) {
      // A parameter already on the link (e.g. a hardcoded campaign) wins.
      if (saved[key] && !url.searchParams.has(key)) {
        url.searchParams.set(key, saved[key]);
      }
    });
    anchor.href = url.toString();
  }

  function onActivate(event) {
    var target = event.target;
    if (!target || !target.closest) return;
    var anchor = target.closest('a[href]');
    if (anchor) decorate(anchor);
  }

  capture(window.location.search);
  window.addEventListener('mintlify:navigate', function (event) {
    if (event.detail && event.detail.search) capture(event.detail.search);
  });

  // Capture phase, so the href is rewritten before the browser reads it to
  // navigate. auxclick covers middle-click open-in-new-tab; mouseover/focusin
  // make the decorated URL visible in the status bar on hover; contextmenu
  // covers right-click → copy link address.
  ['click', 'auxclick', 'mouseover', 'focusin', 'contextmenu'].forEach(function (type) {
    document.addEventListener(type, onActivate, true);
  });
})();

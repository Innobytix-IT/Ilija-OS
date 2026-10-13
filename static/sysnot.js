/* Ilija OS — System-Notifications UI
 * Globale Anzeige persistenter System-Hinweise.
 *
 * - 🔴 kritisch: Vollbild-Overlay nach jedem Seitenaufruf. "Fuer jetzt
 *   wegklicken" per sessionStorage (ueberlebt Reloads, kommt nach
 *   Navigation / neuem Tab wieder). "Erledigt" ruft Server-Resolve auf.
 * - 🟡 warnung: Sticky Banner ganz oben, pro Session dismissbar.
 * - 🔵 info: schwebendes Icon unten rechts, Badge mit Anzahl, Klick
 *   oeffnet Liste. Dismiss nur im Modal.
 *
 * Alle Notifications verschwinden sofort wenn der Server sie resolved
 * (zB "Platte wieder frei" -> next poll laesst sie weg).
 */
(function () {
  "use strict";
  if (window.__ilijaSysnotLoaded) return;
  window.__ilijaSysnotLoaded = true;

  const SS_PREFIX = "ilija_sysnot_dismissed:";
  const POLL_MS   = 60 * 1000;

  function ssGet(key) {
    try { return sessionStorage.getItem(SS_PREFIX + key); } catch(_) { return null; }
  }
  function ssSet(key, val) {
    try { sessionStorage.setItem(SS_PREFIX + key, val); } catch(_) {}
  }

  async function laden() {
    try {
      const r = await fetch("/api/system-notifications", { cache: "no-store" });
      if (!r.ok) return [];
      const data = await r.json();
      return Array.isArray(data) ? data : [];
    } catch (_) { return []; }
  }

  async function erledigen(id) {
    try {
      await fetch(`/api/system-notifications/${id}/resolve`, { method: "POST" });
    } catch (_) {}
    rendern();
  }

  function ensureHost() {
    let host = document.getElementById("ilija-sysnot-host");
    if (host) return host;
    host = document.createElement("div");
    host.id = "ilija-sysnot-host";
    document.body.appendChild(host);
    return host;
  }

  function zeitFormat(iso) {
    try {
      const d = new Date(iso);
      return d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
    } catch (_) { return iso; }
  }

  function cardHtml(n, mitErledigt) {
    const ic = n.level === "kritisch" ? "⚠️" : n.level === "warnung" ? "⚠" : "ℹ";
    const safeTitle = (n.titel || "").replace(/[<>&]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]));
    const safeText  = (n.text  || "").replace(/[<>&]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c])).replace(/\n/g, "<br>");
    return `
      <div class="isn-card isn-${n.level}">
        <div class="isn-ic">${ic}</div>
        <div class="isn-body">
          <div class="isn-titel">${safeTitle}</div>
          <div class="isn-text">${safeText}</div>
          <div class="isn-meta">${zeitFormat(n.erstellt)}</div>
        </div>
        <div class="isn-actions">
          <button class="isn-btn isn-later" data-id="${n.id}" title="Fuer jetzt ausblenden">Spaeter</button>
          ${mitErledigt ? `<button class="isn-btn isn-done" data-id="${n.id}" title="Als erledigt markieren">Erledigt</button>` : ""}
        </div>
      </div>`;
  }

  function rendernOverlayModal(host, kritische) {
    const sichtbar = kritische.filter(n => !ssGet(n.id));
    if (!sichtbar.length) { host.querySelector(".isn-overlay")?.remove(); return; }
    let overlay = host.querySelector(".isn-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "isn-overlay";
      host.appendChild(overlay);
    }
    overlay.innerHTML = `
      <div class="isn-modal">
        <div class="isn-modal-head">
          <span class="isn-modal-titel">⚠️ Wichtige Hinweise (${sichtbar.length})</span>
        </div>
        <div class="isn-modal-list">
          ${sichtbar.map(n => cardHtml(n, true)).join("")}
        </div>
      </div>`;
    overlay.querySelectorAll(".isn-later").forEach(b => {
      b.addEventListener("click", () => { ssSet(b.dataset.id, "1"); rendern(); });
    });
    overlay.querySelectorAll(".isn-done").forEach(b => {
      b.addEventListener("click", () => erledigen(b.dataset.id));
    });
  }

  function rendernBannerStapel(host, warnungen) {
    const sichtbar = warnungen.filter(n => !ssGet(n.id));
    host.querySelector(".isn-banner-wrap")?.remove();
    if (!sichtbar.length) return;
    const wrap = document.createElement("div");
    wrap.className = "isn-banner-wrap";
    wrap.innerHTML = sichtbar.map(n => `
      <div class="isn-banner isn-${n.level}">
        <span class="isn-banner-ic">⚠</span>
        <span class="isn-banner-text"><strong>${(n.titel||"")}</strong> — ${(n.text||"").split("\n")[0]}</span>
        <button class="isn-banner-close" data-id="${n.id}" title="Fuer jetzt ausblenden">✕</button>
      </div>`).join("");
    document.body.insertBefore(wrap, document.body.firstChild);
    wrap.querySelectorAll(".isn-banner-close").forEach(b => {
      b.addEventListener("click", () => { ssSet(b.dataset.id, "1"); rendern(); });
    });
  }

  function rendernInfoIcon(host, infos) {
    host.querySelector(".isn-fab")?.remove();
    if (!infos.length) return;
    const fab = document.createElement("button");
    fab.className = "isn-fab";
    fab.title = `${infos.length} Hinweis${infos.length>1?"e":""}`;
    fab.innerHTML = `<span class="isn-fab-ic">ℹ</span><span class="isn-fab-badge">${infos.length}</span>`;
    fab.addEventListener("click", () => {
      // Modal zum Durchsehen
      let modal = host.querySelector(".isn-info-modal");
      if (modal) { modal.remove(); return; }
      modal = document.createElement("div");
      modal.className = "isn-info-modal";
      modal.innerHTML = `
        <div class="isn-modal">
          <div class="isn-modal-head">
            <span class="isn-modal-titel">Hinweise</span>
            <button class="isn-modal-x">✕</button>
          </div>
          <div class="isn-modal-list">
            ${infos.map(n => cardHtml(n, false)).join("")}
          </div>
        </div>`;
      host.appendChild(modal);
      modal.querySelector(".isn-modal-x").addEventListener("click", () => modal.remove());
      modal.querySelectorAll(".isn-later").forEach(b => {
        b.addEventListener("click", () => { ssSet(b.dataset.id, "1"); modal.remove(); rendern(); });
      });
    });
    host.appendChild(fab);
  }

  let _cache = [];
  async function rendern() {
    const host = ensureHost();
    _cache = await laden();
    rendernOverlayModal(host,  _cache.filter(n => n.level === "kritisch"));
    rendernBannerStapel(host,  _cache.filter(n => n.level === "warnung"));
    rendernInfoIcon(host,      _cache.filter(n => n.level === "info"));
  }

  function start() {
    rendern();
    setInterval(rendern, POLL_MS);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();

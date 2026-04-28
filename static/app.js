const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let currentJobs = [];

const form = $("#search-form");
const submitBtn = $("#submit-btn");
const btnLabel = submitBtn.querySelector(".btn-label");
const btnSpinner = submitBtn.querySelector(".btn-spinner");
const statusPanel = $("#status-panel");
const sourceStatuses = $("#source-statuses");
const counts = $("#counts");
const resultsEl = $("#results");
const filterText = $("#filter-text");
const sortSelect = $("#sort-select");
const exportCsv = $("#export-csv");
const exportJson = $("#export-json");
const toggleAll = $("#toggle-all");

toggleAll.addEventListener("click", (e) => {
  e.preventDefault();
  const boxes = $$('input[name="sources"]:not(:disabled)');
  const allChecked = boxes.every((b) => b.checked);
  boxes.forEach((b) => (b.checked = !allChecked));
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(form);
  const sources = fd.getAll("sources");
  const payload = {
    keywords: fd.get("keywords").trim(),
    location: fd.get("location").trim(),
    contract: fd.get("contract"),
    remote: fd.get("remote") === "on",
    limit: parseInt(fd.get("limit")) || 30,
    max_age_hours: fd.get("max_age_hours") ? parseFloat(fd.get("max_age_hours")) : null,
    sources: sources,
  };
  if (!payload.keywords) {
    alert("Saisis des mots-clés.");
    return;
  }
  if (sources.length === 0) {
    alert("Sélectionne au moins une source.");
    return;
  }

  setLoading(true);
  statusPanel.hidden = false;
  resultsEl.innerHTML = `<div class="empty-state"><div class="icon">⏳</div>Recherche en cours sur ${sources.length} source(s)…</div>`;
  sourceStatuses.innerHTML = "";
  counts.innerHTML = "";

  try {
    const r = await fetch("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Erreur serveur");
    currentJobs = data.jobs;
    renderStatuses(data.statuses);
    counts.innerHTML = `<strong>${data.unique_count}</strong> offres uniques (sur ${data.raw_count} brutes)`;
    exportCsv.disabled = currentJobs.length === 0;
    exportJson.disabled = currentJobs.length === 0;
    renderResults();
  } catch (err) {
    resultsEl.innerHTML = `<div class="empty-state"><div class="icon">❌</div>${err.message}</div>`;
  } finally {
    setLoading(false);
  }
});

function setLoading(loading) {
  submitBtn.disabled = loading;
  btnLabel.hidden = loading;
  btnSpinner.hidden = !loading;
}

function renderStatuses(statuses) {
  const entries = Object.entries(statuses);
  sourceStatuses.innerHTML = entries.map(([name, info]) => {
    let cls = "ok", txt;
    if (info.error) { cls = "err"; txt = info.error; }
    else if (info.count === 0) { cls = "empty"; txt = "0"; }
    else { txt = `<span class="num">${info.count}</span>`; }
    return `<span class="source-status ${cls}" title="${escapeAttr(info.error || '')}">${name} · ${txt}</span>`;
  }).join("");
}

function renderResults() {
  if (currentJobs.length === 0) {
    resultsEl.innerHTML = `<div class="empty-state"><div class="icon">🔎</div>Aucune offre trouvée. Essaie d'autres mots-clés ou élargis la zone.</div>`;
    return;
  }
  const filter = filterText.value.toLowerCase().trim();
  const sortKey = sortSelect.value;
  let jobs = currentJobs.filter((j) => {
    if (!filter) return true;
    return [j.title, j.company, j.location, j.contract]
      .filter(Boolean).some((v) => String(v).toLowerCase().includes(filter));
  });
  jobs.sort((a, b) => {
    if (sortKey === "date") {
      // Tri sur l'ISO parsé quand dispo (sinon les non-parseables tombent en bas).
      const va = a.date_posted_iso || "";
      const vb = b.date_posted_iso || "";
      if (va && vb) return vb.localeCompare(va);
      if (va) return -1;
      if (vb) return 1;
      return 0;
    }
    const va = a[sortKey] || "";
    const vb = b[sortKey] || "";
    return String(vb).localeCompare(String(va));
  });

  if (jobs.length === 0) {
    resultsEl.innerHTML = `<div class="empty-state"><div class="icon">🚫</div>Aucun résultat ne correspond au filtre.</div>`;
    return;
  }

  resultsEl.innerHTML = jobs.map((j) => `
    <div class="job-card">
      <div class="job-main">
        <h3 class="job-title">
          <span class="source-tag src-${j.source}">${escapeHtml(j.source)}</span>
          ${escapeHtml(j.title || "Sans titre")}
        </h3>
        <div class="job-meta">
          <span>🏢 ${escapeHtml(j.company || "—")}</span>
          ${j.location ? `<span>📍 ${escapeHtml(j.location)}</span>` : ""}
          ${j.contract ? `<span>📋 ${escapeHtml(String(j.contract))}</span>` : ""}
          ${j.salary ? `<span>💶 ${escapeHtml(String(j.salary))}</span>` : ""}
          ${j.remote ? `<span>🏠 Remote</span>` : ""}
        </div>
      </div>
      <div class="job-side">
        ${j.url ? `<a href="${escapeAttr(j.url)}" target="_blank" rel="noopener" class="job-link">Voir l'offre →</a>` : ""}
        ${renderDate(j)}
      </div>
    </div>
  `).join("");
}

filterText.addEventListener("input", renderResults);
sortSelect.addEventListener("change", renderResults);

exportCsv.addEventListener("click", () => downloadExport("csv"));
exportJson.addEventListener("click", () => downloadExport("json"));

async function downloadExport(fmt) {
  const r = await fetch(`/export/${fmt}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobs: currentJobs }),
  });
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `offres.${fmt}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function renderDate(j) {
  // Si on a un ISO parsé : affichage relatif + tooltip avec date absolue.
  if (j.date_posted_iso) {
    const dt = new Date(j.date_posted_iso);
    if (!isNaN(dt)) {
      const rel = formatRelative(dt);
      const abs = dt.toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
      const recent = (Date.now() - dt.getTime()) < 24 * 3600 * 1000;
      const cls = recent ? "job-date job-date-fresh" : "job-date";
      return `<span class="${cls}" title="${escapeAttr(abs)}">${escapeHtml(rel)}</span>`;
    }
  }
  // Fallback : afficher le texte brut tel quel (utile pour debug si parser échoue).
  if (j.date_posted) {
    return `<span class="job-date">${escapeHtml(String(j.date_posted))}</span>`;
  }
  return "";
}

function formatRelative(dt) {
  const sec = Math.max(0, (Date.now() - dt.getTime()) / 1000);
  if (sec < 60) return "à l'instant";
  if (sec < 3600) return `il y a ${Math.floor(sec / 60)} min`;
  if (sec < 86400) return `il y a ${Math.floor(sec / 3600)} h`;
  if (sec < 2 * 86400) return "hier";
  if (sec < 7 * 86400) return `il y a ${Math.floor(sec / 86400)} j`;
  if (sec < 30 * 86400) return `il y a ${Math.floor(sec / (7 * 86400))} sem.`;
  // Au-delà d'un mois, montre la date au format DD/MM/YYYY.
  return dt.toLocaleDateString("fr-FR");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

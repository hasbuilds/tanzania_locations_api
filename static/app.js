const $ = (id) => document.getElementById(id);

const regionSelect = $("regionSelect");
const districtSelect = $("districtSelect");
const wardSelect = $("wardSelect");
const streetSelect = $("streetSelect");

const copyPathBtn = $("copyPathBtn");
const resetBtn = $("resetBtn");
const pathBox = $("pathBox");

const searchInput = $("searchInput");
const levelSelect = $("levelSelect");
const searchBtn = $("searchBtn");
const clearSearchBtn = $("clearSearchBtn");
const resultsBox = $("resultsBox");

const healthDot = $("healthDot");
const healthText = $("healthText");

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, m => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[m]));
}

function setHealth(ok, text) {
  healthDot.classList.remove("ok", "bad");
  healthDot.classList.add(ok ? "ok" : "bad");
  healthText.textContent = text;
}

async function apiGet(path) {
  const res = await fetch(path, { headers: { "Accept": "application/json" } });

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;

    try {
      const j = await res.json();
      if (j?.detail !== undefined) {
        detail = (typeof j.detail === "string") ? j.detail : JSON.stringify(j.detail);
      } else {
        detail = JSON.stringify(j);
      }
    } catch {}

    throw new Error(detail);
  }

  return res.json();
}


function resetBrowseUI() {
  districtSelect.innerHTML = `<option value="">Select a region first</option>`;
  wardSelect.innerHTML = `<option value="">Select a district first</option>`;
  streetSelect.innerHTML = `<option value="">Select a ward first</option>`;

  districtSelect.disabled = true;
  wardSelect.disabled = true;
  streetSelect.disabled = true;

  copyPathBtn.disabled = true;
  pathBox.textContent = "—";
}

function updatePath() {
  const r = regionSelect.value;
  const d = districtSelect.value;
  const w = wardSelect.value;
  const s = streetSelect.value;

  const parts = [];
  if (r) parts.push(r);
  if (d) parts.push(d);
  if (w) parts.push(w);
  if (s) parts.push(s);

  pathBox.textContent = parts.length ? parts.join(" / ") : "—";
  copyPathBtn.disabled = parts.length === 0;
}

async function loadRegions() {
  regionSelect.innerHTML = `<option value="">Loading…</option>`;
  const regions = await apiGet(`/regions?limit=500`);
  regionSelect.innerHTML = `<option value="">Select region…</option>` +
    regions.map(r => `<option value="${esc(r.name)}">${esc(r.name)}</option>`).join("");
}

async function loadDistricts(regionName) {
  districtSelect.disabled = true;
  districtSelect.innerHTML = `<option value="">Loading districts…</option>`;

  const districts = await apiGet(`/regions/${encodeURIComponent(regionName)}/districts?limit=1000`);
  districtSelect.innerHTML = `<option value="">Select district…</option>` +
    districts.map(d => `<option value="${esc(d.name)}">${esc(d.name)}</option>`).join("");

  districtSelect.disabled = false;
}

async function loadWards(regionName, districtName) {
  wardSelect.disabled = true;
  wardSelect.innerHTML = `<option value="">Loading wards…</option>`;

  const wards = await apiGet(`/regions/${encodeURIComponent(regionName)}/districts/${encodeURIComponent(districtName)}/wards?limit=2000`);
  wardSelect.innerHTML = `<option value="">Select ward…</option>` +
    wards.map(w => `<option value="${esc(w.name)}">${esc(w.name)}</option>`).join("");

  wardSelect.disabled = false;
}

async function loadStreets(regionName, districtName, wardName) {
  streetSelect.disabled = true;
  streetSelect.innerHTML = `<option value="">Loading streets…</option>`;

  const streets = await apiGet(`/regions/${encodeURIComponent(regionName)}/districts/${encodeURIComponent(districtName)}/wards/${encodeURIComponent(wardName)}/streets?limit=5000`);
  streetSelect.innerHTML = `<option value="">Select street…</option>` +
    streets.map(s => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join("");

  streetSelect.disabled = false;
}

function renderSearchResults(items) {
  if (!items.length) {
    resultsBox.innerHTML = `<div class="muted small">No results.</div>`;
    return;
  }

  resultsBox.innerHTML = items.map(h => `
    <div class="hit">
      <div class="hitTop">
        <div><strong>${esc(h.name)}</strong></div>
        <div class="badge">${esc(h.level)}</div>
      </div>
      <div class="hitPath muted">${esc(h.path)}</div>
      <div class="actions" style="margin-top:10px">
        <button class="ghost" data-copy="${esc(h.path)}">Copy path</button>
      </div>
    </div>
  `).join("");

  // copy buttons
  resultsBox.querySelectorAll("button[data-copy]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const txt = btn.getAttribute("data-copy") || "";
      try {
        await navigator.clipboard.writeText(txt);
        btn.textContent = "Copied!";
        setTimeout(() => (btn.textContent = "Copy path"), 900);
      } catch {
        alert("Clipboard blocked. Copy manually:\n\n" + txt);
      }
    });
  });
}

async function doSearch() {
  const q = searchInput.value.trim();
  if (q.length < 2) {
    resultsBox.innerHTML = `<div class="muted small">Type at least 2 letters.</div>`;
    return;
  }

  resultsBox.innerHTML = `<div class="muted small">Searching…</div>`;
  try {
    const level = levelSelect.value;
    const items = await apiGet(`/search?q=${encodeURIComponent(q)}&level=${encodeURIComponent(level)}&limit=80`);
    renderSearchResults(items);
  } catch (e) {
    resultsBox.innerHTML = `<div class="muted small">Error: ${esc(e.message)}</div>`;
  }
}

async function init() {
  // health
  try {
    const h = await apiGet("/health");
    setHealth(true, `OK • ${h.country} • regions: ${h.regions}`);
  } catch (e) {
    setHealth(false, `API error • ${e.message}`);
  }

  // load regions
  try {
    await loadRegions();
  } catch (e) {
    regionSelect.innerHTML = `<option value="">Failed to load regions</option>`;
    alert("Could not load /regions: " + e.message);
  }

  resetBrowseUI();

  // events
  regionSelect.addEventListener("change", async () => {
    resetBrowseUI();
    const r = regionSelect.value;
    updatePath();
    if (!r) return;

    try {
      await loadDistricts(r);
    } catch (e) {
      alert("Districts error: " + e.message);
      resetBrowseUI();
    }
  });

  districtSelect.addEventListener("change", async () => {
    wardSelect.disabled = true;
    streetSelect.disabled = true;
    wardSelect.innerHTML = `<option value="">Select a district first</option>`;
    streetSelect.innerHTML = `<option value="">Select a ward first</option>`;

    const r = regionSelect.value;
    const d = districtSelect.value;
    updatePath();
    if (!r || !d) return;

    try {
      await loadWards(r, d);
    } catch (e) {
      alert("Wards error: " + e.message);
    }
  });

  wardSelect.addEventListener("change", async () => {
    streetSelect.disabled = true;
    streetSelect.innerHTML = `<option value="">Select a ward first</option>`;

    const r = regionSelect.value;
    const d = districtSelect.value;
    const w = wardSelect.value;
    updatePath();
    if (!r || !d || !w) return;

    try {
      await loadStreets(r, d, w);
    } catch (e) {
      alert("Streets error: " + e.message);
    }
  });

  streetSelect.addEventListener("change", () => updatePath());

  resetBtn.addEventListener("click", () => {
    regionSelect.value = "";
    resetBrowseUI();
    updatePath();
  });

  copyPathBtn.addEventListener("click", async () => {
    const txt = pathBox.textContent;
    if (!txt || txt === "—") return;
    try {
      await navigator.clipboard.writeText(txt);
      copyPathBtn.textContent = "Copied!";
      setTimeout(() => (copyPathBtn.textContent = "Copy selected path"), 900);
    } catch {
      alert("Clipboard blocked. Copy manually:\n\n" + txt);
    }
  });

  searchBtn.addEventListener("click", doSearch);
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
  });

  clearSearchBtn.addEventListener("click", () => {
    searchInput.value = "";
    resultsBox.innerHTML = "";
  });
}

init();

// static/panel.js – upgraded modern panel script
async function apiFetch(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/json",
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  return res.json();
}

// Utility
function show(id) {
  document.getElementById(id).classList.remove("hidden");
}
function hide(id) {
  document.getElementById(id).classList.add("hidden");
}

// Handle Add Proxy modal
document.getElementById("openAdd")?.addEventListener("click", () => show("addModal"));
document.getElementById("closeAdd")?.addEventListener("click", () => hide("addModal"));

async function doAdd() {
  const name = a_name.value.trim();
  const tpl = a_tpl.value.trim();
  const key = a_key.value.trim();
  const loc = a_loc.value;
  const cookie = a_cookie.value.trim() || "x_api_key";
  const strip = a_strip.value.trim();
  const addf = a_add.value.trim();
  const owner = a_owner.value.trim();
  const exp = a_exp.value.trim(); // new expiration field

  if (!name || !tpl || !key) return alert("Name, Template, and Key are required");
  try { if (addf) JSON.parse(addf); } catch { return alert("Invalid add_fields JSON"); }

  const out = await apiFetch("/admin/add_api", {
    method: "POST",
    body: { name, url_template: tpl, api_key: key, key_location: loc, cookie_name: cookie, strip_fields: strip, add_fields: addf, owner_credit: owner, expires_at: exp },
  });

  if (out.success) {
    hide("addModal");
    loadAll();
    alert("Proxy Added Successfully");
  } else alert(out.error || "Failed");
}

async function loadAll() {
  await loadCounts();
  await loadApis();
  await loadLogs();
}

async function loadCounts() {
  const apis = await apiFetch("/admin/list_apis");
  if (Array.isArray(apis)) {
    total.innerText = apis.length;
    const active = apis.filter(a => a.active).length;
    activeCount.innerText = active;
    inactiveCount.innerText = apis.length - active;
  }
  const logs = await apiFetch("/admin/logs");
  if (Array.isArray(logs)) requestsCount.innerText = logs.length;
}

async function loadApis() {
  const apis = await apiFetch("/admin/list_apis");
  const el = document.getElementById("apisTable");
  el.innerHTML = "";
  if (!Array.isArray(apis)) return;

  apis.forEach(a => {
    const proxyUrl = `${a.base_url || ''}/api/${a.api_key}/${a.name}/{term}`;
    const div = document.createElement("div");
    div.className = "card p-4 flex flex-col gap-2 border border-white/10 bg-white/5 rounded-xl";
    div.innerHTML = `
      <div class="flex justify-between items-center">
        <div>
          <div class="font-semibold text-white text-lg">${a.name}</div>
          <div class="text-xs text-slate-400">${a.url_template}</div>
        </div>
        <span class="${a.active ? 'text-emerald-400' : 'text-rose-400'} font-bold">
          ${a.active ? 'Active' : 'Inactive'}
        </span>
      </div>
      <div class="text-xs text-gray-300">Upstream: ${a.url_template}</div>
      <div class="text-xs text-gray-300">Created: ${a.created_at || '-'}</div>
      <div class="text-xs text-gray-300">Expires: ${a.expires_at || 'No limit'}</div>
      <div class="text-xs text-gray-300">Key: <span class="bg-black/40 px-2 py-1 rounded">${a.api_key}</span></div>
      <div class="text-xs text-gray-300">Proxy URL: 
        <input type="text" readonly value="${proxyUrl}" class="bg-black/30 px-2 py-1 rounded w-full text-xs mt-1" onclick="this.select()">
      </div>
      <div class="flex gap-2 mt-2">
        <button class="px-3 py-1 rounded bg-blue-600 text-sm" onclick="editApi(${a.id})">Edit</button>
        <button class="px-3 py-1 rounded bg-rose-600 text-sm" onclick="deleteApi(${a.id})">Delete</button>
      </div>
    `;
    el.appendChild(div);
  });
}

async function editApi(id) {
  const apis = await apiFetch("/admin/list_apis");
  const a = apis.find(x => x.id === id);
  if (!a) return alert("Proxy not found");

  const tpl = prompt("URL Template", a.url_template) || a.url_template;
  const key = prompt("API Key", a.api_key) || a.api_key;
  const loc = prompt("Key Location (query/header/cookie)", a.key_location) || a.key_location;
  const cookie = prompt("Cookie Name", a.cookie_name) || a.cookie_name;
  const strip = prompt("Strip Fields", a.strip_fields || "");
  const addf = prompt("Add Fields JSON", a.add_fields || "");
  const exp = prompt("Expires At (YYYY-MM-DD or empty for none)", a.expires_at || "");
  const owner = prompt("Owner Credit", a.owner_credit || "");

  try { if (addf) JSON.parse(addf); } catch { return alert("Invalid add_fields JSON"); }

  const out = await apiFetch(`/admin/update_api/${id}`, {
    method: "POST",
    body: { url_template: tpl, api_key: key, key_location: loc, cookie_name: cookie, active: a.active, strip_fields: strip, add_fields: addf, owner_credit: owner, expires_at: exp },
  });

  if (out.success) { alert("Updated"); loadAll(); } else alert(out.error || "Failed");
}

async function deleteApi(id) {
  if (!confirm("Delete this proxy?")) return;
  const out = await apiFetch(`/admin/delete_api/${id}`, { method: "POST" });
  if (out.success) { alert("Deleted"); loadAll(); } else alert("Failed");
}

async function loadLogs() {
  const logs = await apiFetch("/admin/logs");
  const el = document.getElementById("logsTable");
  el.innerHTML = "";
  if (!Array.isArray(logs)) return;
  logs.slice(0, 50).forEach(l => {
    const div = document.createElement("div");
    div.className = "bg-white/10 p-2 rounded text-xs text-gray-300";
    div.innerHTML = `${l.created_at} • ${l.client_ip} • ${l.api_name || '-'} • ${l.apitype} • <b>${l.status_code}</b>`;
    el.appendChild(div);
  });
}

window.addEventListener("load", () => { loadAll(); setInterval(loadAll, 15000); });

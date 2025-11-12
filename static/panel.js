// static/panel.js (minimal modern UI behaviour)
async function apiFetch(path, opts={}) {
  const res = await fetch(path, {
    method: opts.method || 'GET',
    headers: Object.assign({'Accept':'application/json','Content-Type':'application/json'}, opts.headers || {}),
    body: opts.body ? JSON.stringify(opts.body) : undefined
  });
  return res.json();
}

function show(el){ el.classList.remove('hidden'); el.classList.add('flex'); }
function hide(el){ el.classList.add('hidden'); el.classList.remove('flex'); }

document.getElementById('openAdd')?.addEventListener('click', ()=>{
  document.getElementById('addModal').classList.remove('hidden');
  document.getElementById('addModal').classList.add('flex');
});

function closeAdd(){
  document.getElementById('addModal').classList.add('hidden');
  document.getElementById('addModal').classList.remove('flex');
}

async function doAdd(){
  const name = document.getElementById('a_name').value.trim();
  const tpl = document.getElementById('a_tpl').value.trim();
  const key = document.getElementById('a_key').value.trim();
  const loc = document.getElementById('a_loc').value;
  const cookie = document.getElementById('a_cookie').value.trim() || 'x_api_key';
  const strip = document.getElementById('a_strip').value.trim();
  const addf = document.getElementById('a_add').value.trim();
  const owner = document.getElementById('a_owner').value.trim();
  if(!name || !tpl || !key) return alert('name, template and key required');
  try{ if(addf) JSON.parse(addf); } catch(e){ return alert('add_fields JSON invalid') }
  const out = await apiFetch('/admin/add_api', { method:'POST', body: { name, url_template: tpl, api_key: key, key_location: loc, cookie_name: cookie, strip_fields: strip, add_fields: addf, owner_credit: owner }});
  if(out.success){ closeAdd(); loadAll(); alert('Added'); } else alert(out.error || 'Failed');
}

async function loadAll(){
  await loadCounts();
  await loadApis();
  await loadLogs();
}

async function loadCounts(){
  const apis = await apiFetch('/admin/list_apis');
  if(Array.isArray(apis)){
    document.getElementById('total').innerText = apis.length;
    const active = apis.filter(a=>a.active).length;
    document.getElementById('active').innerText = active;
    document.getElementById('inactive').innerText = apis.length - active;
  }
  // requests count
  const logs = await apiFetch('/admin/logs');
  if(Array.isArray(logs)) document.getElementById('requests').innerText = logs.length;
}

async function loadApis(){
  const apis = await apiFetch('/admin/list_apis');
  const el = document.getElementById('apisTable');
  el.innerHTML = '';
  if(!Array.isArray(apis)) return;
  apis.forEach(a=>{
    const div = document.createElement('div');
    div.className = 'card p-3 flex items-center justify-between';
    div.innerHTML = `
      <div>
        <div class="font-semibold">${a.name}</div>
        <div class="text-xs text-slate-400">${a.url_template}</div>
      </div>
      <div class="flex items-center gap-3">
        <div class="text-sm text-slate-400">Key: <span class="bg-white/5 px-2 py-1 rounded ml-2">${a.api_key||''}</span></div>
        <div class="${a.active? 'text-emerald-300' : 'text-rose-300'} font-semibold">${a.active? 'Active' : 'Inactive'}</div>
        <button class="px-3 py-1 rounded bg-white/5" onclick="editApi(${a.id})">Edit</button>
        <button class="px-3 py-1 rounded bg-rose-600" onclick="deleteApi(${a.id})">Delete</button>
      </div>
    `;
    el.appendChild(div);
  });
}

async function editApi(id){
  const apis = await apiFetch('/admin/list_apis');
  const a = apis.find(x=>x.id===id);
  if(!a) return alert('not found');
  // show modal populated (simple prompt version)
  const tpl = prompt('URL template', a.url_template) || a.url_template;
  const key = prompt('API key', a.api_key||'') || a.api_key;
  const loc = prompt('key location (query/header/cookie)', a.key_location||'query') || a.key_location;
  const cookie = prompt('cookie name', a.cookie_name||'x_api_key') || a.cookie_name;
  const strip = prompt('strip fields (comma separated)', a.strip_fields||'') ;
  const addf = prompt('add_fields JSON', a.add_fields||'') ;
  const owner = prompt('owner credit', a.owner_credit||'') ;
  try{ if(addf) JSON.parse(addf); } catch(e){ return alert('add_fields JSON invalid') }
  const out = await apiFetch(`/admin/update_api/${id}`, { method:'POST', body: { url_template: tpl, api_key: key, key_location: loc, cookie_name: cookie, active: a.active, strip_fields: strip, add_fields: addf, owner_credit: owner }});
  if(out.success) { alert('Saved'); loadAll(); } else alert(out.error||'failed');
}

async function deleteApi(id){
  if(!confirm('Delete this proxy?')) return;
  const out = await apiFetch(`/admin/delete_api/${id}`, { method:'POST' });
  if(out.success){ alert('Deleted'); loadAll(); } else alert('failed');
}

async function loadLogs(){
  const logs = await apiFetch('/admin/logs');
  const el = document.getElementById('logsTable');
  el.innerHTML = '';
  if(!Array.isArray(logs)) return;
  logs.slice(0,50).forEach(l=>{
    const div = document.createElement('div');
    div.className = 'bg-white/3 p-3 rounded';
    div.innerHTML = `<div class="text-sm">${l.created_at} • ${l.client_ip} • ${l.api_name||'-'} • ${l.apitype} • <strong>${l.status_code}</strong></div>`;
    el.appendChild(div);
  });
}

window.addEventListener('load', ()=>{ loadAll(); setInterval(loadAll,15000); });

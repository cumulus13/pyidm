"""Tiny embedded web UI, served at ``/`` by ``idm --server`` (disable with ``--no-webui``)."""

INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PyIDM WebUI (agent)</title>
<style>
:root{color-scheme:light dark;--bg:#fff;--fg:#1c1f23;--mut:#6b7280;--line:#d8dce2;--acc:#2563eb;--ok:#16a34a;--bad:#dc2626;--warn:#d97706}
@media(prefers-color-scheme:dark){:root{--bg:#14171a;--fg:#e6e8eb;--mut:#9aa3ad;--line:#2b3138;--acc:#60a5fa;--ok:#4ade80;--bad:#f87171;--warn:#fbbf24}}
body{margin:0;font:14px system-ui,sans-serif;background:var(--bg);color:var(--fg)}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:18px;margin:0 0 12px}h2{font-size:14px;margin:18px 0 6px}
form,.bar{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center}
input,textarea{padding:7px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font:inherit}
input[type=text],input[type=password]{flex:1;min-width:150px}
textarea{width:100%;box-sizing:border-box;min-height:64px;font-family:ui-monospace,monospace}
button{padding:6px 12px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);cursor:pointer}
button.p{background:var(--acc);border-color:var(--acc);color:#fff}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:middle}
td.n{max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mut{color:var(--mut)}#msg{color:var(--bad);min-height:1.2em}
.b{padding:1px 8px;border-radius:10px;border:1px solid var(--line);font-size:12px}
.s-complete{color:var(--ok);border-color:var(--ok)}.s-removed,.s-lost{color:var(--mut)}.s-interrupted{color:var(--warn);border-color:var(--warn)}.s-error,.s-failed,.s-cancelled{color:var(--bad);border-color:var(--bad)}
.s-downloading,.s-connecting,.s-finishing,.s-sending{color:var(--acc);border-color:var(--acc)}.s-queued,.s-added,.s-sent{color:var(--warn);border-color:var(--warn)}
</style></head><body><main>
<h1>pyidm agent <span class="mut" id="info"></span></h1>
<div class="bar"><input id="token" type="password" placeholder="token (if the agent requires one)" autocomplete="off">
<button id="save">Connect</button></div>
<form id="add"><textarea id="urls" placeholder="one link per line" required></textarea>
<input id="referrer" type="text" placeholder="referrer (optional)"><input id="path" type="text" placeholder="save path on agent (optional)">
<label><input id="addonly" type="checkbox"> add only (do not start)</label><button class="p">Send to IDM</button></form>
<div id="msg"></div>
<h2>Jobs sent through this agent <button id="clear" type="button">Clear finished</button></h2>
<table><thead><tr><th>Link</th><th>State</th><th>Downloaded</th><th>Speed</th><th>Save as</th><th></th></tr></thead><tbody id="jobs"></tbody></table>
<h2>All IDM downloads <span class="mut">(from IDM log files)</span></h2>
<table><thead><tr><th>Link</th><th>State</th><th>Downloaded</th><th>Speed</th><th>Save as</th></tr></thead><tbody id="dls"></tbody></table>
<script>
const $=id=>document.getElementById(id);let token=sessionStorage.getItem('pyidm-token')||'';$('token').value=token;
const fmt=n=>{if(n==null)return'-';const u=['B','KiB','MiB','GiB','TiB'];let i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toFixed(i?1:0)+' '+u[i]};
async function api(m,p,b){const h={'Content-Type':'application/json'};if(token)h['X-Token']=token;
const r=await fetch(p,{method:m,headers:h,body:b?JSON.stringify(b):undefined});const t=await r.text();let d=null;try{d=t?JSON.parse(t):null}catch(e){}
if(!r.ok)throw new Error((d&&d.error)||r.statusText);return d}
function cell(tr,text,cls){const td=document.createElement('td');td.textContent=text;if(cls)td.className=cls;tr.appendChild(td);return td}
function badge(tr,state){const td=document.createElement('td');const s=document.createElement('span');s.className='b s-'+String(state).replace(/[^a-z]/g,'');s.textContent=state;td.appendChild(s);tr.appendChild(td)}
function fill(id,rows,del){const body=$(id);body.replaceChildren();for(const x of rows){const tr=document.createElement('tr');const d=x.download||x;
cell(tr,x.url||'-','n').title=x.url||'';badge(tr,x.state);cell(tr,fmt(d.downloaded));cell(tr,d.speed!=null?fmt(d.speed)+'/s':'-','mut');cell(tr,d.saveas||'-','n mut');
if(del){const td=document.createElement('td');const b=document.createElement('button');b.textContent='x';b.title='remove from this list (IDM is not touched)';
b.onclick=async()=>{try{await api('DELETE','/jobs/'+encodeURIComponent(x.id));refresh()}catch(e){$('msg').textContent=e.message}};td.appendChild(b);tr.appendChild(td)}
body.appendChild(tr)}}
async function refresh(){try{const[h,j,d]=await Promise.all([api('GET','/health'),api('GET','/jobs'),api('GET','/downloads')]);
$('info').textContent='v'+(h.version||'?')+' - pending '+h.pending+' - IDM log watcher '+(h.watcher?'on':'off');$('msg').textContent='';
fill('jobs',j.jobs,true);fill('dls',d.downloads)}catch(e){$('msg').textContent=e.message}}
$('clear').onclick=async()=>{try{await api('POST','/jobs/clear',{});refresh()}catch(e){$('msg').textContent=e.message}};
$('save').onclick=()=>{token=$('token').value.trim();sessionStorage.setItem('pyidm-token',token);refresh()};
$('add').onsubmit=async e=>{e.preventDefault();const urls=$('urls').value.split('\n').map(s=>s.trim()).filter(Boolean);const b={urls};
if($('referrer').value.trim())b.referrer=$('referrer').value.trim();if($('path').value.trim())b.path=$('path').value.trim();if($('addonly').checked)b.add_only=true;
try{const r=await api('POST','/send',b);$('urls').value='';$('msg').textContent='';refresh()}catch(x){$('msg').textContent=x.message}};
refresh();setInterval(refresh,2000);
</script></main></body></html>
"""

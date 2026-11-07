const $ = (id) => document.getElementById(id);
const money = value => value == null ? 'Unpriced' : (Number(value) > 0 && Number(value) < 0.000001 ? '<$0.000001' : new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:6}).format(Number(value)));
const number = (n) => new Intl.NumberFormat().format(n);
let accessKey = '', departments = [], filter = 'all', editing = null, busy = false;
const escapeHTML = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function departmentIcon(name) {
  const match = [ [/market|brand|content/i, 'marketing'], [/research|develop|science|innovation/i, 'research'], [/engineer|tech|IT\b/i, 'code'], [/support|service/i, 'support'], [/sales|growth|finance/i, 'sales'], [/operation|admin/i, 'operations'], [/people|human|HR\b/i, 'people'] ].find(([pattern]) => pattern.test(name));
  return `<svg class="icon" aria-hidden="true"><use href="/static/icons.svg#${match ? match[1] : 'building'}"></use></svg>`;
}
function status(d) { return d.remaining <= 0 ? 'exhausted' : (d.total_budget > 0 && d.used / d.total_budget >= .8 ? 'warn' : 'active'); }
function notice(message, failure = false) { $('notice').textContent = message; $('notice').className = failure ? 'failure' : ''; $('notice').hidden = false; }
async function api(path, options = {}) {
  const response = await fetch('/api/admin' + path, { ...options, headers: {'Authorization': 'Bearer ' + accessKey, 'Content-Type': 'application/json'}, cache: 'no-store' });
  const data = await response.json();
  if (!response.ok) { if (response.status === 401) lock(); throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the department name and token allocation.'); }
  return data;
}
function lock() {
  clearUsage();
  accessKey = ''; departments = []; $('workspace').hidden = true; $('login').hidden = false; $('logout').hidden = true; $('create').disabled = true;
  $('rows').replaceChildren(); $('new-key').value = ''; $('notice').hidden = true;
  document.querySelectorAll('dialog[open]').forEach(d => d.close());
}
function render() {
  const used = departments.reduce((n,d) => n+d.used,0), total = departments.reduce((n,d) => n+d.total_budget,0), remaining = departments.reduce((n,d) => n+d.remaining,0);
  $('total').textContent = number(total); $('used').textContent = number(used); $('remaining').textContent = number(remaining); $('count').textContent = departments.length; $('badge').textContent = departments.length;
  const priced = departments.reduce((n,d) => n + d.priced_requests, 0), unpriced = departments.reduce((n,d) => n + d.unpriced_requests, 0);
  $('cost-total').textContent = money(priced ? departments.reduce((n,d) => n + Number(d.estimated_cost_usd || 0), 0) : (unpriced ? null : 0));
  $('cost-coverage').textContent = `${number(priced)} priced · ${number(unpriced)} unpriced requests`;
  const attention = departments.filter(d => status(d) !== 'active').length;
  $('attention-count').textContent = attention; $('count-caption').textContent = attention ? `${attention} ${attention === 1 ? 'department needs' : 'departments need'} attention` : 'All departments within budget';
  const search = $('search').value.toLowerCase();
  const visible = departments.filter(d => d.name.toLowerCase().includes(search) && (filter === 'all' || status(d) !== 'active'));
  $('rows').innerHTML = visible.map(d => {
    const state = status(d), percent = d.total_budget > 0 ? d.used / d.total_budget * 100 : (d.used ? 100 : 0);
    return `<tr><td><div class="dept"><span class="avatar c${d.id%4}">${departmentIcon(d.name)}</span><div><strong>${escapeHTML(d.name)}</strong><small>${number(d.requests)} ${d.requests===1?'request':'requests'} recorded</small></div></div></td><td>${number(d.total_budget)}</td><td><div class="usage-number"><span>${number(d.used)}</span><span class="percentage">${Math.round(percent)}%</span></div><div class="bar ${state}"><span style="width:${Math.max(0,Math.min(100,percent))}%"></span></div></td><td>${number(d.remaining)}</td><td><span class="cost-value">${money(d.estimated_cost_usd ?? (d.requests === 0 ? 0 : null))}</span>${d.unpriced_requests ? `<small class="cost-detail">${number(d.unpriced_requests)} unpriced</small>` : ""}</td><td><span class="pill ${state}">${state==='exhausted'?'Exhausted':state==='warn'?'Low balance':'Active'}</span></td><td><button class="edit-button" data-edit="${d.id}" aria-label="Edit budget for ${escapeHTML(d.name)}">Edit budget ↗</button></td></tr>`;
  }).join('');
  $('empty').hidden = visible.length > 0;
  $('empty').querySelector('h3').textContent = departments.length ? 'No matching departments' : 'No departments yet';
  $('empty').querySelector('p').textContent = departments.length ? 'Try another search or switch to all departments.' : 'Create your first department to start allocating tokens.';
  $('row-count').textContent = `Showing ${visible.length} of ${departments.length} departments`;
}
async function refresh() {
  if (!accessKey || busy) return;
  busy = true; $('refresh').disabled = true;
  try { const data = await api('/departments'); if (!accessKey) return; departments = data.departments; render(); syncUsageDepartments(); refreshUsage(); $('updated').textContent = 'Updated ' + new Date().toLocaleTimeString([], {timeZone:'America/New_York',timeZoneName:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
  finally { busy = false; $('refresh').disabled = false; }
}
$('login-form').addEventListener('submit', async e => {
  e.preventDefault(); accessKey = $('staff-key').value.trim(); $('login-error').textContent = '';
  const button = e.submitter; button.disabled = true;
  try { await refresh(); if (!accessKey) return; $('login').hidden = true; $('workspace').hidden = false; $('logout').hidden = false; $('create').disabled = false; $('staff-key').value = ''; }
  catch(e) { accessKey = ''; $('login-error').textContent = e.message; }
  finally { button.disabled = false; }
});
$('logout').onclick = lock;
$('refresh').onclick = () => refresh().catch(e => notice(e.message, true));
$('search').oninput = render;
document.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => {filter = button.dataset.filter; document.querySelectorAll('[data-filter]').forEach(b => b.classList.toggle('selected', b===button)); render();});
function openEditor(department = null) {
  editing = department; $('department-form').reset(); $('form-error').textContent = ''; $('name-field').hidden = !!department; $('department-name').required = !department;
  $('dialog-title').textContent = department ? `Edit ${department.name}` : 'New department'; $('save').textContent = department ? 'Save allocation' : 'Create department';
  $('budget').value = department ? department.total_budget : 10000; $('budget').min = department ? department.used : 0;
  $('budget-help').textContent = department ? `${number(department.used)} tokens already used. Remaining = total allocation minus recorded usage.` : 'This is the department’s total allocation, not an additional top-up.';
  $('editor').showModal();
}
$('create').onclick = () => openEditor();
$('rows').onclick = e => {const button = e.target.closest('[data-edit]'); if (button) openEditor(departments.find(d => d.id === Number(button.dataset.edit)));};
document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => $(b.dataset.close).close());
$('key-dialog').addEventListener('close', () => {$('new-key').value = '';});
document.querySelectorAll('[data-budget]').forEach(b => b.onclick = () => {$('budget').value = b.dataset.budget;});
$('department-form').addEventListener('submit', async e => {
  e.preventDefault(); $('save').disabled = true; $('form-error').textContent = '';
  try {
    const total_budget = Number($('budget').value);
    const data = await api(editing ? `/departments/${editing.id}/budget` : '/departments', {method: editing ? 'PATCH':'POST', body:JSON.stringify(editing ? {total_budget} : {name:$('department-name').value.trim(),total_budget})});
    $('editor').close();
    if (!editing) {$('new-key').value = data.api_key; $('key-title').textContent = `${data.name} is ready`; $('copy-key').textContent = 'Copy key'; $('key-dialog').showModal();}
    notice(editing ? 'Token allocation updated. Recorded usage has been preserved.' : 'Department created. Save its API key before closing.');
    await refresh().catch(e => notice('Saved, but the latest data could not be loaded. ' + e.message, true));
  } catch(e) {$('form-error').textContent = e.message;}
  finally {$('save').disabled = false;}
});
$('copy-key').onclick = async () => {try {await navigator.clipboard.writeText($('new-key').value); $('copy-key').textContent = 'Copied!';} catch { $('new-key').select(); $('copy-key').textContent = 'Select and copy the key'; }};
setInterval(() => {if (accessKey && !document.hidden) refresh().catch(e => notice('Refresh failed. Displayed figures may be out of date. ' + e.message, true));}, 15000);

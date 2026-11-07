/* Usage controls share one filter across the chart and request history. */
let usagePage = 1, usageGeneration = 0;
function syncUsageDepartments() {
  const select = $('usage-department'), selected = select.value;
  select.innerHTML = '<option value="">All departments</option>' + departments.map(d => `<option value="${d.id}">${escapeHTML(d.name)}</option>`).join('');
  select.value = departments.some(d => String(d.id) === selected) ? selected : '';
}
function clearUsage() {
  usageGeneration++;
  $('history-rows').replaceChildren(); $('daily-chart').replaceChildren();
  $('usage-summary').textContent = ''; $('period-cost').textContent = ''; $('usage-error').hidden = true;
  $('activity-summary').textContent = '';
  usagePage = 1;
}
async function refreshUsage() {
  if (!accessKey) return;
  const generation = ++usageGeneration;
  const params = new URLSearchParams({days: $('usage-days').value, page: usagePage});
  if ($('usage-department').value) params.set('department_id', $('usage-department').value);
  $('usage-panel').setAttribute('aria-busy', 'true');
  $('history-prev').disabled = $('history-next').disabled = true;
  try {
    const activityParams = new URLSearchParams(params);
    activityParams.set('status', $('activity-status').value);
    activityParams.set('slow_only', $('activity-slow').checked);
    const [data, activity] = await Promise.all([api('/usage?' + params), api('/activity?' + activityParams)]);
    if (generation !== usageGeneration || !accessKey) return;
    usagePage = activity.page;
    $('usage-error').hidden = true;
    $('usage-summary').textContent = `${number(data.total_tokens)} tokens · ${number(data.total_requests)} successful ${data.total_requests === 1 ? "request" : "requests"} in this period`;
    $('period-cost').textContent = `Estimated cost: ${money(data.estimated_cost_usd ?? (data.total_requests === 0 ? 0 : null))} · ${number(data.priced_requests)} priced / ${number(data.total_requests)} requests`;
    const peak = Math.max(1, ...data.daily.map(d => d.tokens));
    $('chart-scale').textContent = `${number(peak === 1 && data.total_tokens === 0 ? 0 : peak)} tokens`;
    $('daily-chart').innerHTML = data.daily.map((d, i) => {
      const date = new Date(d.date + 'T00:00:00Z').toLocaleDateString(undefined, {month:'short', day:'numeric',timeZone:'UTC'});
      const label = `${date}: ${number(d.tokens)} tokens, ${number(d.requests)} ${d.requests === 1 ? "request" : "requests"}`;
      const showDate = data.days === 7 || i % 5 === 0 || i === data.daily.length-1;
      return `<div class="day-column"><button type="button" class="day-bar" aria-label="${escapeHTML(label)}" style="--bar-height:${d.tokens ? Math.max(1,d.tokens/peak*100) : 0}%"><span class="day-fill"></span><span class="chart-tip">${escapeHTML(label)}</span></button><span class="day-label">${showDate ? escapeHTML(date) : ''}</span></div>`;
    }).join('');
    $('usage-empty').hidden = data.total_requests > 0;
    const counts = activity.status_counts;
    $('activity-summary').textContent = `${number(counts.success || 0)} successful · ${number(counts.blocked || 0)} blocked · ${number((counts.provider_error || 0)+(counts.recording_error || 0))} error(s) in period`;
    $('history-rows').innerHTML = activity.requests.map(r => `<tr><td class="request-id">#${r.id}</td><td>${escapeHTML(r.department)}</td><td><span class="model-tag">${escapeHTML(r.model)}</span></td><td><span class="pill ${r.status === 'success' ? '' : r.status === 'blocked' ? 'warn' : 'exhausted'}">${({success:'Successful',blocked:'Budget blocked',provider_error:'Provider error',recording_error:'Recording error'})[r.status] || escapeHTML(r.status)}</span>${r.error_detail ? `<small class="attempt-detail">${escapeHTML(r.error_detail)}</small>` : ''}</td><td>${r.latency_ms == null ? 'Not recorded' : (r.latency_ms / 1000).toFixed(2) + ' s'}</td><td>${r.tokens == null ? '—' : number(r.tokens)}<small class="cost-detail">${r.tokens == null ? 'Not recorded' : r.input_tokens == null ? 'Breakdown unavailable' : `${number(r.input_tokens)} in · ${number(r.output_tokens)} out · ${number(r.cached_tokens)} cached`}</small></td><td title="${escapeHTML(r.cost_unavailable_reason || (r.status === 'blocked' ? 'Request was not sent to the provider' : r.status !== 'success' ? 'Provider cost could not be determined' : 'Standard text-rate estimate in USD'))}">${r.status === 'blocked' ? 'Not sent' : r.status !== 'success' ? 'Unknown' : money(r.estimated_cost_usd)}</td><td>${escapeHTML(new Date(r.created_at).toLocaleString(undefined,{timeZone:'America/New_York',timeZoneName:'short',year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:true}))}</td></tr>`).join('');
    $('history-empty').hidden = activity.requests.length > 0;
    const pages = Math.max(1, Math.ceil(activity.total_requests/activity.page_size));
    $('history-pagination').textContent = `Page ${activity.page} of ${pages} · ${number(activity.total_requests)} matching ${activity.total_requests === 1 ? "attempt" : "attempts"}`;
    $('history-prev').disabled = activity.page <= 1;
    $('history-next').disabled = activity.page >= pages;
  } catch (error) {
    if (generation !== usageGeneration || !accessKey) return;
    $('usage-error').textContent = 'Usage could not be loaded. Refresh to retry. ' + error.message;
    $('usage-error').hidden = false;
    $('daily-chart').replaceChildren(); $('history-rows').replaceChildren();
    $('usage-summary').textContent = 'Usage unavailable'; $('period-cost').textContent = ''; $('chart-scale').textContent = '';
    $('history-pagination').textContent = ''; $('activity-summary').textContent = ''; $('usage-empty').hidden = $('history-empty').hidden = true;
  } finally {
    if (generation === usageGeneration) $('usage-panel').setAttribute('aria-busy','false');
  }
}
for (const id of ['usage-department','usage-days','activity-status','activity-slow']) $(id).addEventListener('change', () => { usagePage = 1; refreshUsage(); });
$('history-prev').onclick = () => {usagePage--; refreshUsage();};
$('history-next').onclick = () => {usagePage++; refreshUsage();};

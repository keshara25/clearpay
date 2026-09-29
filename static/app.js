'use strict';
const $ = id => document.getElementById(id);
let state = {orders: [], payments: [], sms: []}, filter = 'ALL', selected = null, activeView = 'payments';
const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = n => n == null ? 'Not extracted' : 'LKR ' + (n / 100).toLocaleString('en-LK', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const date = s => s ? new Date(s).toLocaleString('en-GB', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}) : 'Unknown';
const badgeClass = s => s === 'APPROVED' ? 'approved' : s === 'REJECTED' ? 'rejected' : 'pending';
const evidenceLabel = s => s === 'merchant_statement' ? 'Merchant-imported bank record' : s === 'gateway' ? 'Signed merchant gateway' : 'Synthetic test evidence';
const titleCase = s => s.toLowerCase().replace(/(^|\s)\S/g, c => c.toUpperCase());
function toast(text) { $('toast').textContent = text; $('toast').hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => $('toast').hidden = true, 5000); }
async function api(path, options = {}) {
  const response = await fetch('/api' + path, {credentials:'same-origin', ...options});
  let body; try { body = await response.json(); } catch { throw new Error('The server returned an unreadable response.'); }
  if (!response.ok) {
    if (response.status === 401 && path !== '/login') { $('workspace').hidden = true; $('login').hidden = false; }
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Please check the submitted fields.');
  }
  return body;
}
const post = (path, body) => api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
function render() {
  const p = state.payments;
  $('stat-total').textContent = p.length;
  $('stat-approved').textContent = p.filter(x => x.decision.status === 'APPROVED').length;
  $('stat-pending').textContent = p.filter(x => x.decision.status === 'NEEDS VERIFICATION').length;
  $('stat-rejected').textContent = p.filter(x => x.decision.status === 'REJECTED').length;
  $('queue-count').textContent = $('stat-pending').textContent;
  const query = $('search').value.toLowerCase().trim();
  const visible = p.filter(x => (filter === 'ALL' || x.decision.status === filter) &&
    [x.order.customer, x.order_id, x.extraction.reference].join(' ').toLowerCase().includes(query));
  $('result-count').textContent = visible.length;
  $('empty').hidden = visible.length > 0;
  $('payments-body').innerHTML = visible.map(x => `<tr data-id="${esc(x.id)}"><td><div class="person"><span class="avatar">${esc(x.order.customer.split(' ').map(n=>n[0]).slice(0,2).join(''))}</span><span><strong>${esc(x.order.customer)}</strong><span class="sub">${esc(x.order_id)}</span></span></div></td><td>${money(x.extraction.amount_minor)}<span class="sub ref">${esc(x.extraction.reference || 'Reference unreadable')}</span></td><td><span class="badge ${badgeClass(x.decision.status)}">${esc(titleCase(x.decision.status))}</span>${x.decision.incident ? '<span class="sub">⚠ Late evidence conflict</span>' : ''}</td><td class="reason-cell">${esc(titleCase(x.decision.code.replaceAll('_',' ')))}</td><td><span class="sub">${date(x.created_at)}</span></td><td><button class="row-open" aria-label="Review ${esc(x.order_id)}">↗</button></td></tr>`).join('');
  $('payments-body').querySelectorAll('tr').forEach(row => row.addEventListener('click', () => showDetail(row.dataset.id)));
  $('orders-grid').innerHTML = state.orders.map(o => `<article class="info-card"><span class="badge ${o.paid ? 'approved' : ''}">${o.paid ? 'Paid' : 'Awaiting payment'}</span><p class="small">${o.evidence_mode === 'bank_records' ? 'Bank records mode' : 'Test order'}</p><h3>${esc(o.customer)}</h3><p>${esc(o.id)} · ${money(o.amount_minor)}</p><p class="muted small">Transfer memo / payment code</p><code>${esc(o.payment_code)}</code><p class="sub">Account ${esc(o.account)} · Expires ${date(o.expires_at)}</p></article>`).join('') || '<p class="muted">Create your first order to get started.</p>';
  $('sms-list').innerHTML = state.sms.map(s => `<article class="info-card"><span class="badge ${s.trusted && !s.conflict ? 'approved' : ''}">${s.conflict ? 'Conflicting evidence' : s.trusted ? evidenceLabel(s.evidence_source) : 'Parse requires review'}</span><h3 class="ref">${esc(s.reference || 'Unknown reference')}</h3><pre>${esc(s.raw)}</pre><p class="sub">Received ${date(s.received_at)}</p></article>`).join('') || '<p class="muted">No bank notifications received.</p>';
  $('order-select').innerHTML = state.orders.map(o=>`<option value="${esc(o.id)}">${esc(o.id)} · ${esc(o.customer)} · ${money(o.amount_minor)}${o.paid ? ' (paid)' : ''}</option>`).join('');
  $('workspace-mode').textContent = state.settings?.mode === 'bank_records' ? 'Bank records reconciliation' : 'Test workspace';
  $('merchant-summary').textContent = `Receiving account: ${state.account} · ${state.settings?.mode === 'bank_records' ? 'Bank records mode' : 'Test mode'}`;
  $('demo-banner').hidden = !state.demo; $('open-sms').hidden = !state.demo;
  $('seed').hidden = !state.demo || state.orders.length > 0;
}
async function refresh() { state = await api('/dashboard'); render(); }
function field(label, value) { return `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`; }
async function showDetail(id) {
  selected = id;
  const p = state.payments.find(x=>x.id === id), s = p.extraction, o = p.order, d = p.decision;
  $('detail-title').textContent = `${o.customer} · ${o.id}`;
  const bank = state.sms.filter(m=>m.reference === s.reference && (o.evidence_mode !== 'bank_records' || ['gateway','merchant_statement'].includes(m.evidence_source))); 
  const related = state.payments.filter(x=>x.id !== id && ((s.reference && x.extraction.reference === s.reference) || x.image_hash === p.image_hash));
  $('detail-body').innerHTML = `<div class="verdict ${badgeClass(d.status)}">${d.incident ? `<div class="incident">${esc(d.incident)}</div>` : ''}<span class="badge ${badgeClass(d.status)}">${esc(d.status)}</span><h3>${esc(d.reason)}</h3><p>${esc(d.next_action)}</p><small>${esc(d.certainty)} · Policy ${esc(d.policy_version)} · Not a fraud probability</small></div>
  <div class="detail-layout"><div><section class="detail-section"><p class="eyebrow">01 / WHAT THE CUSTOMER SUBMITTED</p><dl class="data-grid">${field('Order mode',o.evidence_mode === 'bank_records' ? 'Bank records' : 'Test / synthetic')}${field('Receipt format',s.receipt_format || 'Labelled receipt')}${field('Submitted amount',money(s.amount_minor))}${field('Expected amount',money(o.amount_minor))}${field('Receiving account',s.account)}${field('Business account',o.account)}${field('Transaction reference',s.reference)}${field('Payment timestamp',s.paid_at)}${field('Slip payment code',s.order_code)}${field('Expected order code',o.payment_code)}</dl><p class="hint">${s.demo_fixture ? 'Synthetic fixture: extraction was seeded for this scenario. Upload an image to test actual OCR.' : `Extraction source: ${esc(s.source)}. Minimum OCR line score: ${Math.round((s.confidence || 0)*100)}%. This measures text recognition, not payment authenticity.`}</p></section><section class="receipt"><img src="/api/payments/${encodeURIComponent(id)}/image" alt="Submitted payment slip for ${esc(o.id)}"><small>Customer-supplied image · Treat as a claim, not proof of receipt.</small></section><details class="detail-section"><summary>Extracted text & reading issues</summary><pre>${esc(s.text)}\n${esc((s.issues || []).join('\n'))}</pre></details></div>
  <div><section class="detail-section"><p class="eyebrow">02 / WHAT THE SYSTEM CONCLUDED</p>${d.checks.map(c=>`<div class="check">✓ ${esc(c.label)}<span>${esc(c.result)}</span></div>`).join('') || '<p class="muted small">Evidence was insufficient before all checks could pass.</p>'}</section><section class="detail-section"><p class="eyebrow">03 / INDEPENDENT BANK EVIDENCE</p>${bank.map(b=>`<p class="small">${esc(evidenceLabel(b.evidence_source))}</p><pre>${esc(b.raw)}</pre>`).join('') || '<p class="hint">No matching eligible bank credit. Import the merchant bank CSV or wait for the signed gateway.</p>'}${state.demo && o.evidence_mode !== 'bank_records' && !bank.length ? '<button id="prepare-sms" class="secondary">Prepare matching demo SMS</button>' : ''}</section><section class="detail-section"><p class="eyebrow">RELATED SUBMISSIONS</p>${related.map(r=>`<p class="small">${esc(r.order_id)} · ${esc(r.order.customer)} · ${esc(r.decision.status)}</p>`).join('') || '<p class="muted small">No matching image or transaction reference found.</p>'}</section><section class="detail-section"><p class="eyebrow">CUSTOMER-SAFE REPLY</p><p id="customer-message" class="customer-msg">${esc(d.customer_message)}</p><button id="copy-reply" class="secondary">Copy reply</button></section><section class="detail-section"><p class="eyebrow">OPERATOR REVIEW</p><label for="review-note">Internal note</label><textarea id="review-note" rows="3" placeholder="Record what you checked and the next action…"></textarea><div class="detail-actions"><button id="save-note" class="secondary">Save note</button><button id="reject-payment" class="secondary" ${d.status==='APPROVED'?'disabled':''}>Reject with reason</button><button id="recheck" class="primary">Recheck</button></div><p class="small muted">Approval requires corroborating evidence. An operator note cannot bypass the rules.</p></section><details><summary>Decision & audit history</summary><div id="audit-list"></div></details></div></div>`;
  if (!$('detail').open) $('detail').showModal();
  $('copy-reply').onclick = async () => { try { await navigator.clipboard.writeText(d.customer_message); toast('Customer reply copied.'); } catch { toast('Select and copy the reply text above.'); } };
  $('recheck').onclick = async () => { try { await post(`/payments/${id}/recheck`, {}); await refresh(); await showDetail(id); toast('Receipt fields refreshed and evidence rechecked.'); } catch(e) { toast(e.message); } };
  const saveReview = async reject => { try { await post(`/payments/${id}/review`, {note:$('review-note').value, reject}); await refresh(); await showDetail(id); toast('Review saved to the audit trail.'); } catch(e) { toast(e.message); } };
  $('save-note').onclick = () => saveReview(false); $('reject-payment').onclick = () => saveReview(true);
  if ($('prepare-sms')) $('prepare-sms').onclick = () => { $('sms-text').value = `Credited LKR ${((s.amount_minor || o.amount_minor)/100).toFixed(2)} to A/C ${o.account}; Ref ${s.reference || 'UNKNOWN'}; Date ${s.paid_at || new Date().toISOString()}; Memo ${o.payment_code}`; $('detail').close(); $('sms-dialog').showModal(); };
  try { const audit = await api(`/payments/${id}/audit`); if(selected===id) $('audit-list').innerHTML = audit.map(a=>`<div class="audit-item"><strong>${esc(a.action.replaceAll('_',' '))}</strong>${date(a.at)} · ${esc(a.actor)}${['REVIEW_NOTE','REJECTED_BY_OPERATOR','SYNTHETIC_FIXTURE'].includes(a.action) ? `<p>${esc(JSON.parse(a.detail).note || JSON.parse(a.detail).scenario)}</p>` : ''}</div>`).join(''); } catch(e) { toast(e.message); }
}
$('login-form').onsubmit = async e => { e.preventDefault(); try { await post('/login',{password:$('password').value}); $('password').value=''; await refresh(); $('login').hidden=true; $('workspace').hidden=false; } catch(e) { $('login-error').textContent=e.message; } };
$('logout').onclick = async()=>{try { await post('/logout',{}); $('workspace').hidden=true; $('login').hidden=false; } catch(e) { toast(e.message); }};
$('refresh').onclick = ()=>refresh().then(()=>toast('Workspace updated.')).catch(e=>toast(e.message));
$('search').oninput = render;
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{ filter=b.dataset.filter; document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t===b)); render(); });
document.querySelectorAll('.nav').forEach(b=>b.onclick=()=>{ activeView=b.dataset.view; document.querySelectorAll('.nav').forEach(t=>t.classList.toggle('active',t===b)); ['payments','orders','bank'].forEach(v=>$(v+'-view').hidden=v!==activeView); $('breadcrumb').textContent=activeView==='payments'?'Payment review':titleCase(activeView); });
document.querySelectorAll('.close').forEach(b=>b.onclick=()=>b.closest('dialog').close());
$('open-submit').onclick=()=>{ if(!state.orders.length){toast('Create an order first.'); $('order-dialog').showModal();}else{$('submit-dialog').showModal();} };
$('open-order').onclick=()=>$('order-dialog').showModal();
$('open-sms').onclick=()=>$('sms-dialog').showModal();
$('open-settings').onclick=()=>{ $('merchant-account').value=state.account; $('merchant-mode').value=state.settings.mode; $('settings-dialog').showModal(); };
$('open-import').onclick=()=>{ if(state.settings.mode!=='bank_records'){ toast('Choose Bank records mode in Merchant setup first.'); $('open-settings').click(); } else { $('import-dialog').showModal(); } };
$('settings-form').onsubmit=e=>handleForm(e,async()=>{ await post('/settings',{account:$('merchant-account').value,mode:$('merchant-mode').value}); toast('Setup saved. Create a new order with these settings.'); });
$('import-form').onsubmit=e=>handleForm(e,async()=>{ const data=new FormData(); data.append('file',$('bank-file').files[0]); data.append('confirmed',String($('bank-confirm').checked)); const result=await api('/bank/import',{method:'POST',body:data}); toast(`${result.imported} bank credits imported; ${result.rechecked} pending payments rechecked.`); $('import-form').reset(); });
async function handleForm(event, action) { event.preventDefault(); const form=event.currentTarget, button=form.querySelector('button[type="submit"],button.primary'), status=form.querySelector('.form-status'); button.disabled=true; status.textContent='Processing…'; try { await action(); status.textContent=''; form.closest('dialog').close(); await refresh(); } catch(e) { status.textContent=e.message; } finally {button.disabled=false;} }
$('order-form').onsubmit=e=>handleForm(e,async()=>{ await post('/orders',{customer:$('customer').value,amount_minor:Math.round(Number($('amount').value)*100)}); toast('Order created. Share its payment code with the customer.'); $('order-form').reset(); });
let pendingUpload = null;
$('slip-file').onchange = () => pendingUpload = null;
$('order-select').onchange = () => pendingUpload = null;
$('submit-form').onsubmit=e=>handleForm(e,async()=>{ const data=new FormData(); data.append('order_id',$('order-select').value); data.append('image',$('slip-file').files[0]); pendingUpload ||= crypto.randomUUID(); const result=await api('/payments',{method:'POST',headers:{'Idempotency-Key':pendingUpload},body:data}); pendingUpload=null; await refresh(); $('submit-dialog').close(); await showDetail(result.id); toast('Payment processed.'); });
$('sms-form').onsubmit=e=>handleForm(e,async()=>{ const result=await post('/demo/sms',{text:$('sms-text').value}); toast(`Notification received. ${result.rechecked} pending submission(s) rechecked.`); });
$('seed').onclick=async()=>{ $('seed').disabled=true; try {await post('/demo/seed',{}); await refresh(); toast('Nine synthetic scenarios loaded.'); }catch(e){toast(e.message);}finally{$('seed').disabled=false;} };
(async()=>{try {const health=await api('/health'); $('login-hint').textContent=health.demo?'Local demo password: demo-operator':'Use your configured business operator password.'; await refresh(); $('login').hidden=true; $('workspace').hidden=false;}catch{}})();

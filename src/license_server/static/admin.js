'use strict';
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const statusNames = {pending:'Chưa kích hoạt',active:'Đang hoạt động',expired:'Đã hết hạn',blocked:'Đã khóa',archived:'Đã lưu trữ'};
const actionNames = {admin_setup:'Tạo tài khoản admin',login:'Đăng nhập',password_changed:'Đổi mật khẩu',key_created:'Tạo key',activated:'Kích hoạt thiết bị',renewed:'Gia hạn key',blocked:'Khóa key',unblocked:'Mở khóa key',device_reset:'Reset thiết bị',note_changed:'Cập nhật ghi chú',backup_downloaded:'Tải bản sao lưu'};
Object.assign(actionNames,{archived:'Lưu trữ key',restored:'Khôi phục key',key_deleted:'Xóa key chưa kích hoạt',audit_cleaned:'Dọn lịch sử cũ'});
let page = 1, pages = 1, auditPage = 1, currentKey = null, toastTimer, searchTimer, requestSequence = 0;
function el(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; }
function date(value) { return value == null ? 'Chưa kích hoạt' : new Intl.DateTimeFormat('vi-VN', {timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value*1000)); }
function toast(message, error=false) {
  const dialogs = [...document.querySelectorAll('dialog[open]')];
  const modal = dialogs.find(item => item.contains(document.activeElement)) || dialogs.at(-1);
  if (error && modal) {
    let feedback = modal.querySelector('[data-feedback]');
    if (!feedback) { feedback = el('p','notice error'); feedback.dataset.feedback='error'; feedback.setAttribute('role','alert'); modal.insertBefore(feedback,modal.querySelector('.dialog-actions')); }
    feedback.textContent=message; $('toast').classList.add('hidden'); return;
  }
  $('toast').textContent = message; $('toast').className = 'toast' + (error ? ' error' : ''); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').classList.add('hidden'), 5500);
}
async function api(path, method='GET', data) {
  const response = await fetch(path, {method, credentials:'same-origin',headers:{'X-CSRF-Token':csrf,...(data !== undefined ? {'Content-Type':'application/json'} : {})}, ...(data !== undefined ? {body:JSON.stringify(data)} : {})});
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401) window.location.assign('/login');
    if (result.error?.code === 'invalid_action' && /\/(delete|archive|restore)$/.test(path)) throw new Error('Máy chủ admin đang chạy bản cũ. Nhấn Ctrl+C trong cửa sổ máy chủ cũ, mở lại Mo_Admin.bat rồi tải lại trang.');
    throw new Error(result.error?.message || 'Không thể hoàn tất yêu cầu.');
  }
  return result;
}
async function busy(button, callback) { if (button.disabled) return; button.disabled = true; try { await callback(); } catch(error) { toast(error.message, true); } finally { button.disabled = false; } }
function badge(status) { return el('span', 'pill ' + status, statusNames[status] || status); }
function download(text, filename) { const url = URL.createObjectURL(new Blob([text], {type:'text/plain;charset=utf-8'})); const a = el('a'); a.href=url; a.download=filename; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000); }
function showCreate() { $('create-dialog').showModal(); }
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('close', () => dialog.querySelector('[data-feedback]')?.remove()));
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.view').forEach(view => view.classList.add('hidden'));
  document.querySelectorAll('[data-view]').forEach(nav => nav.classList.remove('active'));
  button.classList.add('active'); $('view-'+button.dataset.view).classList.remove('hidden');
  if (button.dataset.view === 'audit') loadAudit().catch(e => toast(e.message,true));
}));
$('create-open').addEventListener('click', showCreate); $('empty-create').addEventListener('click', showCreate);
$('password-open').addEventListener('click', () => $('password-dialog').showModal());
$('create-form').addEventListener('submit', event => { event.preventDefault(); busy(event.submitter, async () => {
  const data = new FormData(event.target);
  const result = await api('/api/admin/licenses', 'POST', {days:Number(data.get('days')),quantity:Number(data.get('quantity')),note:data.get('note')});
  $('created-keys').value = result.created.map(item => item.key).join('\n');
  $('create-dialog').close(); $('created-dialog').showModal(); event.target.reset(); page=1;
  await loadKeys();
}); });
$('copy-keys').addEventListener('click', () => busy($('copy-keys'), async () => { try { await navigator.clipboard.writeText($('created-keys').value); toast('Đã sao chép key.'); } catch { $('created-keys').focus(); $('created-keys').select(); toast('Hãy nhấn Ctrl+C để sao chép phần đã chọn.'); } }));
$('download-keys').addEventListener('click', () => download($('created-keys').value+'\n','live-studio-keys.txt'));
$('created-dialog').addEventListener('close', () => { $('created-keys').value=''; });
async function loadKeys() {
  const sequence = ++requestSequence;
  const query = new URLSearchParams({q:$('search').value,status:$('status-filter').value,page:String(page)});
  const result = await api('/api/admin/licenses?'+query);
  if (sequence !== requestSequence) return;
  pages = result.pages;
  if (page > pages) { page = pages; return loadKeys(); }
  for (const key of ['total','active','pending','expired']) $('stat-'+key).textContent = result.stats[key] || 0;
  $('key-count').textContent = result.total + ' key phù hợp';
  const tbody = $('key-rows'); tbody.replaceChildren();
  for (const item of result.items) {
    const row = el('tr'); const identity = el('td');
    identity.append(el('span','key-code',item.key_hint));
    const note = el('span','key-note',item.note || 'Chưa có ghi chú'); note.title=item.note; identity.append(note);
    const plan = el('td','',item.duration_days+' ngày'); if (!item.activated_at) plan.append(el('span','subtext','Từ lần kích hoạt đầu'));
    const state = el('td'); state.append(badge(item.status));
    const device = el('td','',item.device_hint ? 'Đã liên kết' : item.activated_at ? 'Chờ gắn lại' : 'Chưa liên kết'); if (item.device_hint) device.append(el('span','subtext',item.device_hint));
    const expiry = el('td','',date(item.expires_at));
    const controls = el('td'); const manage = el('button','manage','Quản lý'); manage.addEventListener('click', () => busy(manage, () => openKey(item.id))); controls.append(manage);
    row.append(identity,plan,state,device,expiry,controls); tbody.append(row);
  }
  const empty = result.items.length === 0; $('empty-keys').classList.toggle('hidden',!empty);
  $('empty-keys').querySelector('h3').textContent = $('search').value || $('status-filter').value ? 'Không có key phù hợp' : 'Chưa có key nào';
  $('empty-keys').querySelector('p').textContent = $('search').value || $('status-filter').value ? 'Thử thay đổi từ khóa hoặc bộ lọc để xem các key khác.' : 'Tạo key đầu tiên để bắt đầu cấp quyền sử dụng cho khách hàng.';
  $('page-label').textContent = 'Trang '+page+' / '+pages;
  $('prev').disabled=page<=1; $('next').disabled=page>=pages;
}
$('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer=setTimeout(() => {page=1; loadKeys().catch(e => toast(e.message,true));},250); });
$('status-filter').addEventListener('change', () => { page=1; loadKeys().catch(e => toast(e.message,true)); });
$('refresh').addEventListener('click', () => busy($('refresh'),loadKeys));
$('prev').addEventListener('click', () => { if(page>1) {page--;loadKeys().catch(e => toast(e.message,true));} });
$('next').addEventListener('click', () => { if(page<pages) {page++;loadKeys().catch(e => toast(e.message,true));} });
function eventText(item) { let name=actionNames[item.action] || item.action; if(item.detail.days) name+=' · +'+item.detail.days+' ngày'; if(item.detail.duration_days) name+=' · '+item.detail.duration_days+' ngày'; if(item.action==='audit_cleaned') name+=' · '+item.detail.count+' bản ghi'; return name; }
async function openKey(id) {
  const result = await api('/api/admin/licenses/'+encodeURIComponent(id)); currentKey=result.license;
  $('detail-title').textContent = currentKey.key_hint; $('detail-note').value=currentKey.note;
  const box = $('detail-info'); box.replaceChildren();
  for (const [name,value] of [['Trạng thái',statusNames[currentKey.status]],['Gói ban đầu',currentKey.duration_days+' ngày'],['Kích hoạt lần đầu',date(currentKey.activated_at)],['Hết hạn',date(currentKey.expires_at)],['Thiết bị',currentKey.device_hint || 'Chưa liên kết'],['Kiểm tra gần nhất',currentKey.last_check ? date(currentKey.last_check) : 'Chưa có']]) { const cell=el('div'); cell.append(el('label','',name),el('strong','',value));box.append(cell); }
  $('block-key').textContent=currentKey.blocked ? 'Mở khóa key' : 'Khóa key'; $('reset-device').disabled=!currentKey.device_hint;
  $('block-key').disabled=Boolean(currentKey.archived);
  $('archive-key').classList.toggle('hidden',currentKey.activated_at == null);
  $('archive-key').textContent=currentKey.archived ? 'Khôi phục key' : 'Lưu trữ key';
  $('delete-key').classList.toggle('hidden',currentKey.activated_at != null);
  const events=$('detail-audit'); events.replaceChildren();
  for(const item of result.audit.slice(0,15)) { const node=el('div','event'); node.append(el('strong','',eventText(item)),el('p','',date(item.at)+' · '+(item.actor==='client'?'Ứng dụng khách':item.actor)));events.append(node); }
  if (!$('detail-dialog').open) $('detail-dialog').showModal();
}
async function mutate(action,data={}) { await api('/api/admin/licenses/'+currentKey.id+'/'+action,'POST',data); await openKey(currentKey.id); await loadKeys(); }
$('note-form').addEventListener('submit', event => {event.preventDefault();busy(event.submitter,async()=>{await mutate('note',{note:$('detail-note').value});toast('Đã lưu ghi chú.');});});
$('renew-form').addEventListener('submit', event => {event.preventDefault();busy(event.submitter,async()=>{await mutate('renew',{days:Number($('renew-days').value)});toast('Đã gia hạn key.');});});
function confirmAction(title, message, callback) { $('confirm-dialog').querySelector('[data-feedback]')?.remove(); $('confirm-title').textContent=title; $('confirm-text').textContent=message; $('confirm-submit').onclick=()=>busy($('confirm-submit'),async()=>{await callback();$('confirm-dialog').close();}); $('confirm-dialog').showModal(); }
$('block-key').addEventListener('click', () => {const unblock=Boolean(currentKey.blocked);confirmAction(unblock?'Mở khóa key?':'Khóa key?',unblock?'Cho phép kiểm tra giấy phép trở lại. Thời hạn vẫn giữ nguyên.':'Ứng dụng khách sẽ bị từ chối ở lần kiểm tra giấy phép tiếp theo.',async()=>{await mutate(unblock?'unblock':'block');toast(unblock?'Đã mở khóa key.':'Đã khóa key.');});});
$('reset-device').addEventListener('click', () => confirmAction('Reset liên kết thiết bị?','Máy cũ sẽ không vượt qua lần kiểm tra giấy phép tiếp theo. Khách cần kích hoạt lại; ngày hết hạn vẫn giữ nguyên.',async()=>{await mutate('reset-device');toast('Đã reset thiết bị.');}));
$('password-form').addEventListener('submit', event => {event.preventDefault();busy(event.submitter,async()=>{const form=new FormData(event.target);await api('/api/admin/password','POST',Object.fromEntries(form));window.location.assign('/login');});});
async function loadAudit() { const result=await api('/api/admin/audit?page='+auditPage);$('audit-rows').replaceChildren();for(const item of result.items){const row=el('tr');row.append(el('td','',date(item.at)),el('td','',eventText(item)),el('td','',item.key_hint || (item.license_id ? item.license_id.slice(0,12) : 'Hệ thống')),el('td','',item.actor==='client'?'Ứng dụng khách':item.actor));$('audit-rows').append(row);}$('audit-page').textContent='Trang '+auditPage;$('audit-prev').disabled=auditPage<=1;$('audit-next').disabled=result.items.length<50; }
$('audit-prev').addEventListener('click',()=>{if(auditPage>1){auditPage--;loadAudit().catch(e=>toast(e.message,true));}});
$('audit-next').addEventListener('click',()=>{auditPage++;loadAudit().catch(e=>toast(e.message,true));});
const archivedOption=el('option','','Đã lưu trữ'); archivedOption.value='archived'; $('status-filter').append(archivedOption);
const detailActions=$('block-key').parentElement;
const archiveButton=el('button','','Lưu trữ key'); archiveButton.id='archive-key'; detailActions.append(archiveButton);
const deleteButton=el('button','danger','Xóa vĩnh viễn'); deleteButton.id='delete-key'; detailActions.append(deleteButton);
archiveButton.addEventListener('click',()=>{const restore=Boolean(currentKey.archived);confirmAction(restore?'Khôi phục key?':'Lưu trữ key?',restore?'Key trở lại danh sách ở trạng thái khóa. Bạn cần mở khóa riêng để cho phép sử dụng.':'Ngừng quyền sử dụng và ẩn key khỏi danh sách mặc định. Có thể khôi phục qua bộ lọc Đã lưu trữ.',async()=>{await mutate(restore?'restore':'archive');toast(restore?'Đã khôi phục; key vẫn đang khóa.':'Đã lưu trữ key.');});});
deleteButton.addEventListener('click',()=>confirmAction('Xóa key vĩnh viễn?','Chỉ xóa key chưa từng kích hoạt. Key sẽ không thể sử dụng hoặc khôi phục; lịch sử mã rút gọn vẫn được giữ.',async()=>{const id=currentKey.id;await api('/api/admin/licenses/'+id+'/delete','POST',{});$('detail-dialog').close();currentKey=null;await loadKeys();toast('Đã xóa key chưa kích hoạt.');}));
const auditActions=el('div','heading-actions');
const exportLink=el('a','button','Tải lịch sử JSON');exportLink.href='/api/admin/audit/export';auditActions.append(exportLink);
const cleanButton=el('button','','Dọn lịch sử cũ');auditActions.append(cleanButton);$('view-audit').querySelector('.page-heading').append(auditActions);
cleanButton.addEventListener('click',()=>busy(cleanButton,async()=>{const preview=await api('/api/admin/audit/cleanup-preview');if(!preview.count){toast('Không có lịch sử cũ hơn 180 ngày.');return;}confirmAction('Dọn '+preview.count+' bản ghi cũ?','Xóa lịch sử trước '+date(preview.cutoff)+'. Key và hạn sử dụng vẫn được giữ. Bạn có thể Hủy để tải lịch sử trước khi dọn.',async()=>{const result=await api('/api/admin/audit/cleanup','POST',{cutoff:preview.cutoff});auditPage=1;await loadAudit();toast('Đã dọn '+result.deleted+' bản ghi.');});}));
const configLink=el('a','button','Cấu hình kết nối tool');configLink.href='/api/admin/client-config';document.querySelector('#view-guide .guide').prepend(configLink);
loadKeys().catch(error=>toast(error.message,true));

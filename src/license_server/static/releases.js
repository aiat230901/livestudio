'use strict';
async function loadRelease() {
  try {
    const result = await api('/api/admin/releases');
    const payload = result.latest?.payload;
    $('release-status').textContent = payload ? 'Phiên bản '+payload.version+' · '+Math.round(payload.size/1024/1024)+' MB\n'+payload.notes : 'Chưa có bản phát hành. Chọn ZIP và tệp thông tin đã ký để bắt đầu.';
    $('release-download').classList.toggle('hidden', !payload);
    if(payload) $('release-download').href='/api/releases/download/'+payload.sha256+'.zip';
  } catch(error) { $('release-status').textContent=error.message; }
}
document.querySelector('[data-view="releases"]').addEventListener('click',loadRelease);
$('release-form').addEventListener('submit', event => {
  event.preventDefault();
  busy(event.submitter, async () => {
    const file=$('release-zip').files[0], manifest=$('release-manifest').files[0];
    if(!file || !manifest || manifest.size>32768) throw new Error('Chọn ZIP và tệp JSON hợp lệ.');
    const envelope=JSON.parse(await manifest.text());
    if(envelope.payload?.size!==file.size) throw new Error('ZIP và tệp JSON không cùng bản phát hành.');
    const header=btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(envelope))));
    const chunkSize=256*1024;
    for(let offset=0;offset<file.size;offset+=chunkSize) await new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();
      xhr.open('POST','/api/admin/releases');
      xhr.timeout=30*60*1000;
      xhr.setRequestHeader('X-CSRF-Token',csrf);
      xhr.setRequestHeader('X-Release-Manifest',header);
      xhr.setRequestHeader('X-Upload-Offset',String(offset));
      xhr.setRequestHeader('Content-Type','application/octet-stream');
      xhr.upload.onprogress=e=>{$('release-progress').textContent='Đang tải… '+Math.round((offset+e.loaded)/file.size*100)+'%. Giữ trang này mở.';};
      xhr.onload=()=>{
        let body; try{body=JSON.parse(xhr.responseText);}catch{reject(new Error('Hosting không nhận được gói. Kiểm tra giới hạn dung lượng tải lên.'));return;}
        if(xhr.status>=200&&xhr.status<300) resolve(body);
        else reject(new Error(body.error?.message||'Không phát hành được.'));
      };
      xhr.onerror=xhr.ontimeout=()=>reject(new Error('Kết nối tải lên bị gián đoạn. Bản hiện tại được giữ; bạn có thể thử lại.'));
      xhr.send(file.slice(offset,offset+chunkSize));
    });
    $('release-progress').textContent='Phát hành thành công. Khách mở tool sẽ được kiểm tra phiên bản mới.';
    event.target.reset(); await loadRelease();
  });
});

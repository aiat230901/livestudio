// Exercise the real feedback/confirmation functions without a browser or user data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../src/license_server/static/admin.js'),'utf8');
const button = {disabled:false};
const modal = {
  open:true, feedback:null,
  contains(node) {return node === button;},
  querySelector(selector) {return selector === '[data-feedback]' ? this.feedback : button;},
  insertBefore(node) {this.feedback=node;node.remove=()=>{this.feedback=null;};},
  showModal() {this.open=true;}, close() {this.open=false;}
};
const globalToast = {classList:{add() {}},textContent:''};
const nodes = {'toast':globalToast,'confirm-dialog':modal,'confirm-submit':button,'confirm-title':{},'confirm-text':{}};
const context = {
  $:id=>nodes[id], csrf:'test', toastTimer:null,
  document:{activeElement:button,querySelectorAll:()=>modal.open?[modal]:[]},
  el:()=>({dataset:{},setAttribute() {}}),
  setTimeout:()=>1,clearTimeout() {},
  fetch:async()=>({ok:false,status:400,json:async()=>({error:{code:'invalid_action',message:'old server'}})}),
  window:{location:{assign() {}}}
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function toast('),source.indexOf('function badge(')),context);
vm.runInContext(source.slice(source.indexOf('function confirmAction('),source.indexOf("$('block-key').addEventListener")),context);
(async()=>{
  context.confirmAction('Delete?','Test key only',()=>context.api('/api/admin/licenses/test/delete','POST',{}));
  await button.onclick();
  assert.equal(modal.open,true,'Failed delete must keep confirmation open');
  assert.equal(button.disabled,false,'User must be able to retry');
  assert.match(modal.feedback.textContent,/Mo_Admin\.bat/,'Stale server needs actionable feedback inside the modal');
  assert.equal(globalToast.textContent,'','Error must not be hidden in a background toast');
  let succeeded=false;
  context.confirmAction('Delete?','Test key only',async()=>{succeeded=true;});
  assert.equal(modal.feedback,null,'Old errors must clear before a new confirmation');
  await button.onclick();
  assert.equal(succeeded,true);
  assert.equal(modal.open,false,'Successful operation closes the confirmation');
  console.log('Admin confirmation feedback: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

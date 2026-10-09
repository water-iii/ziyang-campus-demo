const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const C=require('./engine.js');
const elements={'app-main':{innerHTML:''},'app-nav':{innerHTML:''},'top-section':{textContent:''},'toast':{className:'',textContent:''}};
const callbacks={}; const store={};
const document={getElementById(id){return elements[id] || (elements[id]={innerHTML:''});},addEventListener(type,fn){callbacks[type]=fn;}};
const localStorage={getItem(key){return store[key]||null},setItem(key,val){store[key]=val}};
const window={DemoCore:C,scrollTo(){},confirm(){return true}};
const context={document,window,localStorage,setTimeout(){return 0},clearTimeout(){},console};
vm.runInNewContext(fs.readFileSync('./app.js','utf8'),context,{filename:'app.js'});
const target=(sel,data)=>({closest(q){return q===sel?{dataset:data,disabled:false}:null;}});
function click(act,more={}){callbacks.click({target:target('[data-action]',{action:act,...more})});}
function page(p){callbacks.click({target:target('[data-page]',{page:p})});assert.ok(elements['app-main'].innerHTML.length>1200,`Page ${p} failed`);}
for(const p of ['dashboard','student','merchant','driver','campus','issues'])page(p);
page('student');click('add-item',{product:'p11'});click('place-order');
page('dashboard');click('cutoff');
for(const m of ['m1','m2','m3']){page('merchant');click('merchant-accept',{mid:m});click('merchant-pack',{mid:m});}
page('driver');click('pickup',{mid:'m1'});click('pickup',{mid:'m2'});click('pickup-short',{mid:'m3'});click('depart');
page('campus');click('receive');click('assign');click('complete');
page('issues');click('resolve',{issue:'EX001'});
const state=JSON.parse(store['ziyang-camp-lunch-demo-v01']);
assert.equal(state.batch.status,'finished');assert.equal(state.orders.length,31);assert.equal(state.issues[0].status,'resolved');
assert.ok(elements['app-main'].innerHTML.includes('班次贡献'));
console.log('PASS: all 6 UI views render; click handlers complete student order, cutoff, 3-store packing, shortage pickup, delivery and refund.');

import test from 'node:test';
import assert from 'node:assert/strict';

const storage = new Map();
globalThis.localStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) };
const { progress, imagePaths, discoverJob, operationKey, terminal, intentCaption, kindLabel, jobView } = await import('../web/jobs.js?v=studio-2');
const { draft, saveDraft, clearDraft } = await import('../web/drafts.js?v=studio-2');
const { element, action, lightbox } = await import('../web/ui.js?v=studio-2');

test('一枚の拡大画面にnull文字を追加せず、複数画像の移動は維持する', () => {
  class FakeNode {
    constructor() { this.children = []; this.events = {}; }
    setAttribute() {}
    append(...children) { this.children.push(...children.map(x => x instanceof FakeNode ? x : String(x))); }
    replaceChildren(...children) { this.children = children; }
    addEventListener(name, fn) { this.events[name] = fn; }
    showModal() {}
  }
  globalThis.Node = FakeNode;
  globalThis.document = {body:new FakeNode(), createElement:()=>new FakeNode(), createElementNS:()=>new FakeNode(), createTextNode:text=>text};
  lightbox([{path:'a'}]);
  assert.equal(document.body.children[0].children.length, 2);
  lightbox([{path:'a'},{path:'b'}]);
  assert.equal(document.body.children[1].children.length, 3);
  assert.equal(document.body.children[1].children[2].children.length, 2);
});

test('only measured progress is shown; indeterminate jobs get no percentage', () => {
  assert.equal(progress({kind:'image',status:'running'}),null);
  assert.deepEqual(progress({kind:'lora_train',progress:{step:12,total:1200}}),{value:12,total:1200,unit:'step'});
  assert.deepEqual(progress({kind:'character_bible',completed_panels:3,total_panels:23}),{value:3,total:23,unit:'パネル'});
  assert.deepEqual(progress({kind:'preview',pictures:[{path:'a'}],total_images:2}),{value:1,total:2,unit:'枚'});
  assert.equal(terminal({status:'failed'}),true);
});
test('a previous or ambiguous job is never claimed by a new request', () => {
  const old = {job_id:'old',kind:'preview',name:'Bell',style:''};
  const recent = {...old,job_id:'new'};
  const spec = {kind:'preview',name:'Bell',style:''};
  assert.equal(discoverJob([old],spec,['old']),null);
  assert.deepEqual(discoverJob([old,recent],spec,['old']),recent);
  assert.equal(discoverJob([recent,{...recent,job_id:'another'}],spec,['old']),null);
  assert.equal(discoverJob([{...recent,style:'other'}],spec,['old']),null);
  assert.equal(operationKey(spec),operationKey({style:'',name:'Bell',kind:'preview'}));
});
test('解釈の確認待ちと採用済みを処理中として数えない', () => {
  for (const status of ['draft', 'awaiting_confirmation', 'confirmed']) {
    assert.equal(terminal({kind:'intent',status}),true);
    assert.ok(intentCaption({kind:'intent',status}));
  }
  assert.equal(terminal({kind:'intent',status:'running'}),false);
  assert.equal(terminal({kind:'preview',status:'draft'}),false);
  assert.equal(kindLabel('intent'),'注文の解釈');
});
test('教材確認待ちはGPU処理中にも学習完了にも見せない', () => {
  const job = {kind:'lora_train',status:'awaiting_confirmation',progress:{step:0,total:1200}};
  assert.equal(terminal(job),true);
  assert.equal(progress(job),null);
  assert.equal(intentCaption(job),'教材の確認待ち・学習は未開始');
  class FakeNode { constructor(){this.attributes={};this.children=[];} setAttribute(k,v){this.attributes[k]=v;} append(...children){this.children.push(...children);} addEventListener(){} }
  globalThis.Node = FakeNode;
  globalThis.document = {createElement:()=>new FakeNode(),createElementNS:()=>new FakeNode(),createTextNode:text=>text};
  const view = jobView(job, {startedAt:'2026-09-05T00:00:00Z'});
  const all = node => [node, ...node.children.filter(child=>child instanceof FakeNode).flatMap(all)];
  assert.ok(!view.className.includes('completed'));
  assert.ok(!all(view).some(node => /working|indeterminate|elapsed/.test(node.className || '')));
});
test('all final pictures are collected without duplicated sheets', () => {
  assert.deepEqual(imagePaths({sheet_path:'sheet',path:'sheet',pictures:[{path:'a'}],candidates:[{path:'b'}]}),['sheet','a','b']);
});
test('saving one draft preserves every other picture and an empty caption', () => {
  saveDraft('Bell:1',''); saveDraft('Bell:2','coat');
  clearDraft('Bell:1');
  assert.equal(draft('Bell:2'),'coat');
  saveDraft('Bell:1',''); assert.equal(draft('Bell:1','old caption'),'');
});
test('null and false attributes never silently select options or disable controls', () => {
  class FakeNode { constructor(){this.attributes={};this.children=[];} setAttribute(k,v){this.attributes[k]=v;} append(...children){this.children.push(...children);} addEventListener(){} }
  globalThis.Node = FakeNode;
  globalThis.document = {createElement:()=>new FakeNode(),createTextNode:text=>text};
  const option = element('option',{selected:null,disabled:false,value:'Bell'},0);
  assert.deepEqual(option.attributes,{value:'Bell'}); assert.deepEqual(option.children,['0']);
  assert.deepEqual(element('option',{selected:true}).attributes,{selected:''});
});
test('duplicate clicks do not repeat a pending mutation', async () => {
  const control = {disabled:false,setAttribute(){},removeAttribute(){}};
  let resolve; let calls=0;
  const pending = action(control,()=>{calls++;return new Promise(done=>{resolve=done;});});
  await action(control,()=>{calls++;}); assert.equal(calls,1); assert.equal(control.disabled,true);
  resolve(); await pending; assert.equal(control.disabled,false);
});

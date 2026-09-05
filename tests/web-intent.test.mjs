import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.localStorage = {getItem: () => null, setItem() {}};
class FakeNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.value = ''; }
  setAttribute(key, value) { this.attrs[key] = value; if (key === 'value') this.value = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  get lastChild() { return this.children.at(-1); }
  remove() {}
  addEventListener(name, fn) { (this.events ||= {})[name] = fn; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
}
globalThis.Node = FakeNode;
globalThis.document = {createElement: tag => new FakeNode(tag), createElementNS: (_namespace, tag) => new FakeNode(tag), createTextNode: text => text, querySelector: () => new FakeNode('notice')};
const {API} = await import('../web/api.js?v=studio-2');
const {commentEditor} = await import('../web/intent.js?v=studio-2');
const {characterStrength} = await import('../web/strength.js?v=studio-2');
const {previewIntentJob, drawingInput} = await import('../web/flows.js?v=studio-2');
const all = root => [root, ...root.children.filter(x => x instanceof FakeNode).flatMap(all)];
const next = () => new Promise(resolve => setImmediate(resolve));

test('研究中の強度を明示保存し、ゼロ・再表示・既定値への復帰を扱う', async () => {
  let saved = {name:'確認用'};
  const calls = [];
  API.setCharacterStrength = async (name, strength) => { calls.push([name, strength]); saved = {...saved, character_strength:strength}; return saved; };
  const root = characterStrength(saved);
  const input = all(root).find(n => n.attrs['aria-label'] === 'キャラクターの特徴の強さ');
  input.reportValidity = () => root.disabled || input.value !== '';
  assert.equal(input.value, '0.8');
  assert.equal(calls.length, 0);
  input.value = '';
  await all(root).find(n => n.tag === 'button' && n.children.includes('特徴の強さを保存')).events.click();
  assert.equal(calls.length, 0);
  input.value = '0';
  await all(root).find(n => n.tag === 'button' && n.children.includes('特徴の強さを保存')).events.click();
  assert.deepEqual(calls, [['確認用', 0]]);
  assert.equal(all(characterStrength(saved)).find(n => n.tag === 'input').value, '0');
  await all(root).find(n => n.tag === 'button' && n.children.includes('既定値に戻す')).events.click();
  assert.equal(input.value, '0.8');
  assert.deepEqual(calls.at(-1), ['確認用', 0.8]);
});

test('コメント反映に研究中の表示と画像確認の説明がある', async () => {
  API.commentIntents = async () => [];
  const root = new FakeNode('root');
  await commentEditor(root, {name:'確認用',kind:'character',stage:'preview'});
  const texts = all(root).flatMap(n => n.children.filter(c => typeof c === 'string'));
  assert.ok(texts.includes('研究中の機能'));
  assert.ok(texts.some(text => text.includes('十分に反映されない場合')));
});

test('特徴ごとの参照画像を、文章の説明に依存せず表示する', async () => {
  const refs = [0, 1, 2, 3].map(i => ({record_key:'probe',sample_index:i,path:`${i}.png`}));
  API.commentIntents = async () => [{job_id:'refs',stage:'samples',panel:'',status:'awaiting_confirmation',references:refs,
    original_comment:'',proposal:{observations:[],questions:[],changes:[
      {feature:'face',scope:'persistent',panel_key:null,reference:refs[1],description_en:'oval face',avoid_en:'',avoid_ja:'',reason_ja:'顔'},
      {feature:'outfit',scope:'persistent',panel_key:null,reference:refs[3],description_en:'separate top and skirt',avoid_en:'',avoid_ja:'',reason_ja:'服'}]}}];
  const root = new FakeNode('root');
  await commentEditor(root, {name:'確認用',kind:'character',stage:'samples'});
  const texts = all(root).flatMap(n => n.children.filter(c => typeof c === 'string'));
  assert.ok(texts.includes('顔の参照元：画像 2'));
  assert.ok(texts.includes('衣装の参照元：画像 4'));
});

test('画風は全体の選択として表示し、明示保留でも衣装の訂正を採用できる', async t => {
  t.mock.method(globalThis, 'setTimeout', () => 0);
  let saved = {job_id:'style-order',status:'awaiting_confirmation',stage:'sheet',panel:'',original_comment:'画風と衣装の注文',references:[],
    available_styles:[{name:'水彩',note:'登録済み',lora_name:'water.safetensors'}],
    panel_specs:[{key:'turn_front',section:'向き',label:'正面'}],
    proposal:{questions:[],observations:[],changes:[
      {feature:'style',scope:'this_run',panel_key:null,reference:null,description_en:'',avoid_en:'',avoid_ja:'',reason_ja:'画風は未解決',style_name:null,style_deferred:false},
      {feature:'outfit',scope:'this_run',panel_key:null,reference:null,description_en:'blue coat',avoid_en:'',avoid_ja:'',reason_ja:'衣装'}]}};
  API.commentIntents = async()=>[structuredClone(saved)];
  API.confirmComment = async(_id, proposal)=>{ saved={...saved,status:'confirmed',accepted:structuredClone(proposal)}; return structuredClone(saved); };
  const root = new FakeNode('root');
  await commentEditor(root,{name:'確認用',kind:'character',stage:'sheet'});
  const nodes=all(root);
  assert.ok(nodes.find(n=>n.attrs['aria-label']==='採用する画風'));
  assert.ok(nodes.some(n=>n.tag==='option' && n.attrs.value==='""' && n.children.includes('追加の画風を使わない（キャラクターLoRAのみ）')));
  assert.ok(!nodes.find(n=>n.attrs['aria-label']==='描き方の対象パネル'));
  assert.ok(!nodes.find(n=>n.attrs['aria-label']==='描き方の生成文'));
  const scope=nodes.find(n=>n.attrs['aria-label']==='画風の適用範囲');
  assert.ok(!scope.children.some(n=>n.attrs?.value==='panel'));
  nodes.find(n=>n.attrs['aria-label']==='衣装の生成文').events.input({target:{value:'navy coat'}});
  nodes.find(n=>n.attrs['aria-label']==='画風の希望を保留する').events.change({target:{checked:true}});
  const button=all(root).find(n=>n.tag==='button'&&n.children.includes('この内容を採用'));
  await button.events.click({currentTarget:button});
  assert.equal(saved.accepted.changes[0].style_deferred,true);
  assert.equal(saved.accepted.changes[1].description_en,'navy coat');
  assert.ok(all(root).some(n=>n.textContent === '採用済みです。画風の希望は保留中です'));
});

test('保存応答が逆転しても、新しい原文と解釈対象を維持する', async () => {
  API.commentIntents = async () => [];
  API.character = async () => ({samples: []});
  const pending = [];
  API.saveComment = body => new Promise(resolve => pending.push({body, resolve}));
  const root = new FakeNode('root');
  const editor = await commentEditor(root, {name:'確認用', kind:'character', stage:'preview'});
  const input = all(root).find(node => node.attrs['aria-label'] === '制作への注文');
  input.value = '古い注文'; const first = editor.save(); await next();
  input.value = '新しい注文'; const second = editor.save(); await next();
  const newer = {job_id:'new', status:'draft', references:[]};
  pending[1].resolve(newer); await second;
  pending[0].resolve({job_id:'old', status:'draft', references:[]}); await first;
  assert.equal(await editor.save(), newer);
  assert.equal(pending.length, 2);
  assert.deepEqual(pending.map(item => item.body.comment), ['古い注文', '新しい注文']);
});

test('パネルの原文を選択中のパネルへ保存する', async () => {
  API.commentIntents = async () => [];
  API.character = async () => ({samples:[{index:3,path:'four.png',caption:''} ]});
  let body;
  API.saveComment = async request => { body = request; return {status:'draft',references:[]}; };
  const root = new FakeNode('root');
  const editor = await commentEditor(root, {name:'確認用',kind:'character',stage:'panel',panel:'turn_front',interpretEnabled:false});
  all(root).find(node => node.attrs['aria-label'] === '制作への注文').value = 'このパネルの注文';
  await editor.save();
  assert.equal(body.stage, 'panel'); assert.equal(body.panel, 'turn_front');
  assert.deepEqual(body.sample_indices, [3]);
});

test('未採用の注文があっても、別経路の自由入力には解釈IDを付けない', () => {
  const editor = {confirmedJob() { throw new Error('未確認'); }};
  assert.equal(previewIntentJob(editor, 'side view'), '');
  assert.throws(() => previewIntentJob(editor, 'full body, standing, front view, looking at viewer'), /未確認/);
});

test('一枚生成は明示した入力方法で注文を選び、残っている自由英文に切り替えない', () => {
  const editor = {confirmedJob:()=> 'adopted'};
  assert.deepEqual(drawingInput(editor,'intent','old English'), {prompt:'',intentJobId:'adopted'});
  const pending = {confirmedJob(){throw new Error('未確認');}};
  assert.throws(()=>drawingInput(pending,'intent','old English'),/未確認/);
  assert.deepEqual(drawingInput(pending,'english','a tree'), {prompt:'a tree',intentJobId:''});
  assert.throws(()=>drawingInput(editor,'english','  '),/内容/);
});

test('教材の観察は希望とは別の編集欄へ表示する', async () => {
  const reference = {record_key:'probe',sample_index:3,path:'four.png'};
  API.commentIntents = async () => [{job_id:'job',status:'awaiting_confirmation',stage:'training',panel:'',original_comment:'青にしたい',references:[reference],proposal:{observations:[{reference,appearance_ja:'白い服',caption_en:'white outfit'}],changes:[],questions:['どんな青？']}}];
  const root = new FakeNode('root');
  await commentEditor(root, {name:'確認用',kind:'character',stage:'training'});
  const fields = all(root);
  assert.ok(fields.find(node => node.attrs['aria-label'] === '画像 1 の観察'));
  assert.ok(fields.find(node => node.attrs['aria-label'] === '画像 1 の教材説明'));
  assert.ok(fields.find(node => node.tag === 'button' && node.children.includes('この画像説明を教材に採用')));
  assert.ok(fields.find(node => node.tag === 'p' && node.children.includes('どんな青？')));
});

test('設定画の同じ衣装特徴でも、全体と対象パネルの範囲を訂正して別々に採用する', async t => {
  t.mock.method(globalThis,'setTimeout',()=>0);
  let saved = {job_id:'sheet-order',status:'awaiting_confirmation',stage:'sheet',panel:'',original_comment:'衣装の注文',references:[],
    panel_specs:[{key:'turn_front',section:'向き',label:'正面'},{key:'item_shoes',section:'単品',label:'靴'}],
    proposal:{questions:[],observations:[],changes:[
      {feature:'outfit',scope:'persistent',panel_key:null,reference:null,description_en:'coat',avoid_en:'',avoid_ja:'',reason_ja:'全体の衣装'},
      {feature:'outfit',scope:'this_run',panel_key:'item_shoes',reference:null,description_en:'red boots',avoid_en:'',avoid_ja:'',reason_ja:'今回の靴'}]}};
  API.commentIntents = async()=>[structuredClone(saved)];
  API.confirmComment = async(_id,proposal)=> { saved={...saved,status:'confirmed',accepted:structuredClone(proposal)}; return structuredClone(saved); };
  const root = new FakeNode('root');
  await commentEditor(root,{name:'確認用',kind:'character',stage:'sheet'});
  const scopes = all(root).filter(n=>n.attrs['aria-label']==='衣装の適用範囲');
  scopes[1].events.change({target:{value:'panel'}});
  const targets = all(root).filter(n=>n.attrs['aria-label']==='衣装の対象パネル');
  targets[1].events.change({target:{value:'item_shoes'}});
  const control = all(root).find(n=>n.tag==='button' && n.children.includes('この内容を採用'));
  await control.events.click({currentTarget:control});
  assert.deepEqual(saved.accepted.changes.map(c=>[c.feature,c.scope,c.panel_key]),[
    ['outfit','persistent',null],['outfit','panel','item_shoes']]);
  assert.equal(saved.accepted.changes[1].description_en,'red boots');
});

for (const first of ['observations', 'wish']) test(`${first}を先に採用しても、もう片方の訂正を失わない`, async t => {
  t.mock.method(globalThis, 'setTimeout', () => 0);
  const reference = {record_key:'probe',sample_index:3,path:'four.png'};
  let saved = {job_id:'job',status:'awaiting_confirmation',stage:'training',panel:'',original_comment:'青にしたい',references:[reference],proposal:{observations:[{reference,appearance_ja:'白い服',caption_en:'white outfit'}],changes:[{feature:'outfit',scope:'persistent',panel_key:null,reference,description_en:'blue outfit',avoid_en:'',avoid_ja:'',reason_ja:'青にする'}],questions:[]}};
  API.commentIntents = async () => [structuredClone(saved)];
  API.confirmObservations = async (_id, observations) => { saved.accepted_observations = structuredClone(observations); return structuredClone(saved); };
  API.confirmComment = async (_id, proposal) => { saved.status = 'confirmed'; saved.accepted = structuredClone(proposal); return structuredClone(saved); };
  const root = new FakeNode('root');
  await commentEditor(root, {name:'確認用',kind:'character',stage:'training'});
  const field = label => all(root).find(node => node.attrs['aria-label'] === label);
  for (const [label, value] of [['衣装の生成文','navy blue outfit'], ['画像 1 の教材説明','white top and skirt']]) field(label).events.input({target:{value}});
  const click = async label => { const control = all(root).find(node => node.tag === 'button' && node.children.includes(label)); await control.events.click({currentTarget:control}); };
  const labels = first === 'observations' ? ['この画像説明を教材に採用','この内容を採用'] : ['この内容を採用','この画像説明を教材に採用'];
  await click(labels[0]);
  assert.ok(field('衣装の生成文').children.includes('navy blue outfit'));
  assert.ok(field('画像 1 の教材説明').children.includes('white top and skirt'));
  await click(labels[1]);
  assert.equal(saved.accepted.changes[0].description_en, 'navy blue outfit');
  assert.equal(saved.accepted_observations[0].caption_en, 'white top and skirt');
});

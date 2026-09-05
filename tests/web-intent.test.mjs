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
const {previewIntentJob} = await import('../web/flows.js?v=studio-2');
const all = root => [root, ...root.children.filter(x => x instanceof FakeNode).flatMap(all)];
const next = () => new Promise(resolve => setImmediate(resolve));

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

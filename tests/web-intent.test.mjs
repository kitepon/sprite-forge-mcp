import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.localStorage = {getItem: () => null, setItem() {}};
class FakeNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.value = ''; }
  setAttribute(key, value) { this.attrs[key] = value; if (key === 'value') this.value = value; }
  addEventListener() {}
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
}
globalThis.Node = FakeNode;
globalThis.document = {createElement: tag => new FakeNode(tag), createTextNode: text => text};
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

import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.localStorage = { getItem: () => null, setItem() {} };
class FakeNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.value = ''; this.classList = { add() {}, remove() {}, toggle() {} }; }
  setAttribute(k, v) { this.attrs[k] = v; if (k === 'value') this.value = v; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(k, v) { (this.events ||= {})[k] = v; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
  insertBefore(item, before) { this.children.splice(this.children.indexOf(before), 0, item); }
  get lastChild() { return this.children.at(-1); }
  remove() {}
}
globalThis.Node = FakeNode;
globalThis.document = { createElement: tag => new FakeNode(tag), createElementNS: (_, tag) => new FakeNode(tag), createTextNode: text => text, querySelector: () => new FakeNode('notice') };
const { API } = await import('../web/api.js?v=studio-2');
const { samples } = await import('../web/flows.js?v=studio-2');
const { pendingFiles, saveDraft } = await import('../web/drafts.js?v=studio-2');
const { referenceNotes, saveCaption } = await import('../web/intent.js?v=studio-2');
const all = node => [node, ...node.children.filter(c => c instanceof FakeNode).flatMap(all)];

for (const kind of ['character', 'style']) test(`${kind}：画像選択だけで追加し、完了まで次へ進めない`, async t => {
  t.mock.method(URL, 'createObjectURL', () => 'blob:test');
  t.mock.method(URL, 'revokeObjectURL', () => {});
  let record = { samples: [] }, uploaded = 0, ready = false;
  API[kind] = async () => structuredClone(record);
  API.commentIntents = async () => [];
  API.upload = async () => [{ path: `upload-${++uploaded}` }];
  const commits = [];
  API[kind === 'character' ? 'addSamples' : 'addStyleSamples'] = (_name, path) => new Promise(resolve => commits.push(() => {
    record.samples.push({ index: record.samples.length, path, caption: '' }); resolve(structuredClone(record));
  }));
  const root = new FakeNode('root'), cleanup = [];
  const save = await samples(root, kind, kind, cleanup, () => {}, value => { ready = value; });
  const file = all(root).find(n => n.attrs.type === 'file'); file.files = [{ name: 'a' }, { name: 'b' }];
  file.events.change(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(ready, false); assert.equal(uploaded, 1);
  commits.shift()(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(ready, false); assert.equal(uploaded, 2);
  commits.shift()(); await pendingFiles.get(`${kind}:${kind}`).promise;
  assert.equal(ready, true); assert.equal(record.samples.length, 2);
  assert.ok(!all(root).some(n => n.children.includes('選んだ画像を追加')));
  await save(); cleanup.forEach(fn => fn());
});

test('追加途中の失敗は成功分を保ち、再送は未追加分だけを処理する', async t => {
  t.mock.method(URL, 'createObjectURL', () => 'blob:test'); t.mock.method(URL, 'revokeObjectURL', () => {});
  t.mock.method(globalThis, 'setTimeout', () => 0);
  let record = { samples: [] }, uploads = 0, fail = true;
  API.character = async () => structuredClone(record); API.commentIntents = async () => [];
  API.upload = async () => [{ path: `p-${++uploads}` }];
  API.addSamples = async (_, path) => {
    if (path === 'p-2' && fail) throw new Error('保存できません');
    record.samples.push({ index: record.samples.length, path, caption: '' }); return structuredClone(record);
  };
  const root = new FakeNode('root'), cleanup = []; let ready;
  await samples(root, 'character', '再送', cleanup, () => {}, r => { ready = r; });
  const input = all(root).find(n => n.attrs.type === 'file'); input.files = [{ name: 'a' }, { name: 'b' }]; input.events.change();
  const pending = pendingFiles.get('character:再送'); await pending.promise;
  assert.equal(ready, false); assert.equal(record.samples.length, 1); assert.equal(pending.length, 1);
  fail = false;
  all(root).find(n => n.children.includes('追加できなかった画像を再送する')).events.click(); await pending.promise;
  assert.equal(uploads, 2); assert.equal(record.samples.length, 2); assert.equal(ready, true);
  cleanup.forEach(fn => fn());
});

test('希望の自動保存と移動時の保存が重なっても、古い入力を後から書かない', async () => {
  API.commentIntents = async () => [];
  const calls = []; let release;
  API.saveComment = async body => { calls.push(body.comment); if (calls.length === 1) await new Promise(resolve => { release = resolve; }); return body; };
  const notes = await referenceNotes(new FakeNode('root'), { name: '保存順', kind: 'character' });
  notes.input.value = '古い希望'; const first = notes.save(); await new Promise(resolve => setImmediate(resolve));
  notes.input.value = '新しい希望'; const second = notes.save();
  assert.deepEqual(calls, ['古い希望']); release(); await Promise.all([first, second]);
  assert.deepEqual(calls, ['古い希望', '新しい希望']);
});

test('画像コメントの自動保存も順序を保つ', async () => {
  const calls = []; let release;
  API.setCaption = async (_name, _index, value) => { calls.push(value); if (calls.length === 1) await new Promise(resolve => { release = resolve; }); };
  const sample = { index: 0, path: 'image', caption: '' };
  saveDraft('character:保存順:caption:0:image', '古い希望');
  const first = saveCaption('character', '保存順', sample, '古い希望'); await new Promise(resolve => setImmediate(resolve));
  saveDraft('character:保存順:caption:0:image', '新しい希望');
  const second = saveCaption('character', '保存順', sample, '新しい希望'); release(); await Promise.all([first, second]);
  assert.deepEqual(calls, ['古い希望', '新しい希望']);
});

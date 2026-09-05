import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.localStorage = { getItem: () => null, setItem() {} };
class FakeNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.value = ''; }
  setAttribute(key, value) { this.attrs[key] = value; if (key === 'value') this.value = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  get lastChild() { return this.children.at(-1); }
  addEventListener(name, fn) { (this.events ||= {})[name] = fn; }
  append(...items) { this.children.push(...items); }
  replaceChildren(...items) { this.children = items; }
}
globalThis.Node = FakeNode;
globalThis.document = { createElement: tag => new FakeNode(tag), createElementNS: (_, tag) => new FakeNode(tag), createTextNode: text => text, querySelector: () => new FakeNode('notice') };
const { API } = await import('../web/api.js?v=studio-2');
const { layoutEditor, layoutValues } = await import('../web/layout.js?v=studio-2');
const all = root => [root, ...root.children.filter(x => x instanceof FakeNode).flatMap(all)];
const find = (root, label) => all(root).find(n => n.attrs['aria-label'] === label) || all(root).find(n => n.children.includes(label));
const click = async (root, label) => { const node = find(root, label); assert.ok(node, label); await node.events.click({ currentTarget: node }); };
const change = (root, label, value) => { const node = find(root, label); node.value = value; node.events.input({ target: node }); };
const panel = (key, label, seed_offset) => ({ key, section: '体', label, kind: 'full', parts: [{ feature: 'pose', description_en: 'side view', avoid_en: '' }], role_features: ['pose'], inherited_features: ['subject'], seed_offset });
const setup = () => {
  let saved = [panel('side', '側面', 2), panel('front', '正面', 0)];
  API.sheetLayout = async () => structuredClone(saved);
  API.commentIntents = async () => [];
  API.character = async () => ({ samples: [] });
  API.saveLayout = async (name, expected, panels) => { assert.deepEqual(expected, saved); saved = structuredClone(panels); return saved; };
  return () => saved;
};

test('手動の並べ替えと名称変更を保存し、再表示でも保つ', async () => {
  const saved = setup(); const root = new FakeNode('root');
  const editor = await layoutEditor(root, '手動確認'); editor.requireConfirmed();
  assert.equal(all(root).filter(n => n.tag === 'input' && n.attrs.type === 'checkbox').length, 22);
  await click(root, '正面を上へ');
  change(root, '項目 1 の名前', '前から');
  assert.throws(editor.requireConfirmed, /構成を確定/);
  await click(root, 'この構成を確定'); editor.requireConfirmed();
  assert.deepEqual(saved().map(p => [p.key, p.label, p.seed_offset]), [['front', '前から', 0], ['side', '側面', 2]]);
  const reloaded = new FakeNode('root'); await layoutEditor(reloaded, '手動確認');
  assert.equal(find(reloaded, '項目 1 の名前').value, '前から');
});

test('追加した項目の内容を確定し、内部キーを利用者に入力させない', async () => {
  const saved = setup(); const root = new FakeNode('root'); const editor = await layoutEditor(root, '追加確認');
  await click(root, '項目を追加');
  change(root, '新しい項目の被写体・体形・体色（英語）', 'a small dragon');
  await click(root, 'この構成を確定'); editor.requireConfirmed();
  assert.equal(saved().length, 3); assert.match(saved()[2].key, /^custom_/); assert.equal(saved()[2].seed_offset, 3);
  assert.equal(saved()[2].parts[0].description_en, 'a small dragon');
  assert.ok(!all(root).some(n => n.attrs['aria-label']?.includes('key')));
});

test('編集中の構成も解釈へ送り、確定は描画の注文と分ける', async () => {
  const saved = setup(); const root = new FakeNode('root'); let job;
  API.saveComment = async body => { job = { job_id: 'layout-job', original_comment: body.comment, working_layout: body.layout_panels, stage: 'layout', status: 'draft', references: [] }; return structuredClone(job); };
  API.interpretComment = async () => { job.status = 'awaiting_confirmation'; job.proposal = { summary_ja: '並べ替えました', questions: [], panels: job.working_layout.map(p => ({ ...p, description_ja: p.label, reference: null })) }; return structuredClone(job); };
  API.confirmLayout = async (id, proposal) => { assert.equal(id, 'layout-job'); await API.saveLayout('解釈確認', saved(), layoutValues(proposal.panels)); job = { ...job, status: 'confirmed', accepted: proposal, confirmed_layout: saved() }; return job; };
  const editor = await layoutEditor(root, '解釈確認'); await click(root, '正面を上へ');
  change(root, 'シート構成への注文', 'この並びで');
  await click(root, '言葉から構成案を作る');
  assert.equal(job.working_layout[0].key, 'front'); assert.throws(editor.requireConfirmed, /構成/);
  await click(root, 'この構成を確定'); assert.equal(editor.requireConfirmed(), undefined);
  assert.equal(saved()[0].key, 'front');
});

test('原文の変更と解釈待ちは生成を開始できず、再表示で下書きを保つ', async () => {
  setup(); const root = new FakeNode('root'); const editor = await layoutEditor(root, '下書き確認');
  change(root, 'シート構成への注文', '参考画像の衣装を追加');
  assert.throws(editor.requireConfirmed, /構成/);
  const second = new FakeNode('root'); const restored = await layoutEditor(second, '下書き確認');
  assert.equal(find(second, 'シート構成への注文').value, '参考画像の衣装を追加');
  assert.throws(restored.requireConfirmed, /構成/);
});

test('別操作で保存が変わった下書きは再表示で競合を示す', async () => {
  const saved = setup(); const root = new FakeNode('root');
  await layoutEditor(root, '競合確認'); change(root, '項目 1 の名前', '古い下書き');
  const updated = structuredClone(saved()); updated[0].label = '別操作の名前';
  await API.saveLayout('競合確認', saved(), updated);
  const second = new FakeNode('root'); const editor = await layoutEditor(second, '競合確認');
  assert.throws(editor.requireConfirmed, /構成/);
  assert.ok(all(second).some(n => n.textContent?.includes('別の操作で更新')));
  await click(second, '下書きを保存済み構成に戻す'); editor.requireConfirmed();
  assert.equal(find(second, '項目 1 の名前').value, '別操作の名前');
});

test('重複する特徴の優先指定は一つにまとめ、残った特徴の指定を保つ', async () => {
  const saved = setup();
  const duplicated = structuredClone(saved());
  duplicated[0].parts.push({ feature: 'pose', description_en: 'standing', avoid_en: '' });
  await API.saveLayout('特徴確認', saved(), duplicated);
  const root = new FakeNode('root'); await layoutEditor(root, '特徴確認');
  const roleLabel = '側面の姿勢・向きを項目固有にする';
  assert.equal(all(root).filter(n => n.attrs['aria-label'] === roleLabel).length, 1);
  const role = find(root, roleLabel);
  role.events.change({ target: { checked: false } });
  await click(root, 'この構成を確定');
  assert.deepEqual(saved()[0].role_features, []);
  role.events.change({ target: { checked: true } });
  find(root, '側面の特徴 1').events.change({ target: { value: 'outfit' } });
  await click(root, 'この構成を確定');
  assert.deepEqual(saved()[0].parts.map(p => p.feature), ['outfit', 'pose']);
  assert.deepEqual(saved()[0].role_features, ['pose', 'outfit']);
  assert.equal(all(root).filter(n => n.attrs['aria-label'] === roleLabel).length, 1);
});

test('不採用にした案は原文入力を戻し、再表示で復活しない', async () => {
  const saved = setup();
  let job = { job_id: 'discard-me', status: 'awaiting_confirmation', stage: 'layout', original_comment: 'いったん取り消す注文', proposal: { summary_ja: '', questions: [], panels: saved().map(p => ({ ...p, description_ja: p.label, reference: null })) } };
  API.commentIntents = async () => [structuredClone(job)];
  API.discardLayout = async id => { assert.equal(id, job.job_id); job.status = 'discarded'; };
  const root = new FakeNode('root'); const editor = await layoutEditor(root, '取消確認');
  await click(root, '下書きを保存済み構成に戻す'); editor.requireConfirmed();
  assert.equal(find(root, 'シート構成への注文').value, '');
  assert.equal(job.original_comment, 'いったん取り消す注文');
  const second = new FakeNode('root'); const restored = await layoutEditor(second, '取消確認');
  restored.requireConfirmed();
  assert.equal(find(second, 'シート構成への注文').value, '');
});

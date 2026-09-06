import test from 'node:test';
import assert from 'node:assert/strict';
globalThis.localStorage = { getItem: () => null, setItem() {} };
class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.value = ''; this.attrs = {}; }
  setAttribute(key, value) { this.attrs[key] = value; }
  addEventListener(key, value) { (this.events ||= {})[key] = value; }
  append(...children) { this.children.push(...children); if (this.tag === 'textarea') this.value = this.children.join(''); }
  replaceChildren(...children) { this.children = children; }
}
globalThis.Node = Node;
globalThis.document = { createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag), createTextNode: text => text };
const { previewReviewCard, reviewLabel } = await import('../web/preview.js?v=studio-2');
const { API } = await import('../web/api.js?v=studio-2');
const all = node => [node, ...node.children.filter(n => n instanceof Node).flatMap(all)];
const initial = {id:'image-a',path:'/image-a.png',review:{rating:'',comment:'',focus:[],revision:0,history:[]}};

test('NGの理由欄を明示し、判定を変えても原文を維持して同じ画像へ順序通り保存する', async () => {
  assert.equal(reviewLabel('ng'), 'この画像のどこがNGでしたか？');
  const calls = [];
  API.savePreviewReview = async (name, job, image, review) => { calls.push({name,job,image,...review}); return {...review,revision:review.revision+1,history:[]}; };
  const card = previewReviewCard('ベル','job-a',structuredClone(initial),0,()=>{});
  const nodes = all(card.node), textarea = nodes.find(n=>n.tag==='textarea');
  nodes.find(n=>n.children.includes('NG：直したい画像')).events.click();
  textarea.value='髪型が違う。衣装は合っている'; textarea.events.input();
  await card.flush();
  nodes.find(n=>n.children.includes('未判定')).events.click();
  await card.flush();
  assert.equal(calls.at(-1).comment,'髪型が違う。衣装は合っている');
  assert.equal(calls.at(-1).rating,'');
  assert.ok(calls.every(call=>call.image==='image-a' && call.job==='job-a'));
  assert.deepEqual(calls.map(call=>call.revision),calls.map((_,i)=>i));
  card.dispose();
});

test('保存中に元の判定へ戻した操作も保存する', async () => {
  let release;
  const waiting = new Promise(resolve => { release = resolve; });
  const calls = [];
  API.savePreviewReview = async (_, __, ___, review) => {
    calls.push(review.rating);
    if (calls.length === 1) await waiting;
    return {...review, revision: review.revision + 1, history: []};
  };
  const card = previewReviewCard('ベル', 'job-a', {...initial, review: {...initial.review, rating: 'ok', revision: 1}}, 0, () => {});
  const nodes = all(card.node);
  nodes.find(n => n.children.includes('NG：直したい画像')).events.click();
  await Promise.resolve();
  nodes.find(n => n.children.includes('OK：残したい画像')).events.click();
  release();
  await card.flush();
  assert.deepEqual(calls, ['ng', 'ok']);
  assert.equal(card.rating(), 'ok');
  card.dispose();
});

test('保存後に届いた古い取得結果で判定と理由を戻さない', async () => {
  API.savePreviewReview = async (_, __, ___, review) => ({...review, revision: review.revision + 1, history: []});
  const card = previewReviewCard('ベル', 'job-a', structuredClone(initial), 0, () => {});
  const nodes = all(card.node), textarea = nodes.find(n => n.tag === 'textarea');
  nodes.find(n => n.children.includes('NG：直したい画像')).events.click();
  textarea.value = '髪型を直したい';
  await card.flush();
  card.update(structuredClone(initial.review));
  assert.equal(card.rating(), 'ng');
  assert.equal(textarea.value, '髪型を直したい');
  card.dispose();
});

test('保存失敗を表示し、再読込みで入力中のコメントを上書きしない', async () => {
  API.savePreviewReview=async()=>{throw new Error('通信が切れました');};
  const card=previewReviewCard('ベル','job-a',structuredClone(initial),0,()=>{});
  const nodes=all(card.node), textarea=nodes.find(n=>n.tag==='textarea');
  nodes.find(n=>n.children.includes('NG：直したい画像')).events.click();
  textarea.value='残すべき入力';
  await assert.rejects(card.flush(),/通信が切れました/);
  card.update({...initial.review,revision:8,comment:'別の画面の入力'});
  assert.equal(textarea.value,'残すべき入力');
  assert.ok(nodes.some(n=>n.textContent?.includes('判定を保存できませんでした')));
  card.dispose();
});

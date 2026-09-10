import test from 'node:test';
import assert from 'node:assert/strict';
import { Node, installDom, all } from './web-dom.mjs';
installDom();
const { previewReviewCard, reviewLabel, focusLabel, meaningSummary } = await import('../web/preview.js');
const { API } = await import('../web/api.js');
const strings = node => all(node).flatMap(n => n.children.filter(c => typeof c === 'string'));
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

test('NGの場所は寄せ先、OKの場所は記録だと表示する', async () => {
  API.savePreviewReview = async (_, __, ___, review) => ({...review, revision: review.revision + 1, history: []});
  const card = previewReviewCard('ベル', 'job-a', structuredClone(initial), 0, () => {});
  const nodes = all(card.node);
  assert.equal(focusLabel(''), 'OK・NGを選んでから場所を選べます');
  assert.ok(nodes.some(n => n.textContent === focusLabel('')));
  nodes.find(n => n.children.includes('NG：直したい画像')).events.click();
  assert.ok(nodes.some(n => n.textContent === focusLabel('ng')));
  nodes.find(n => n.children.includes('OK：残したい画像')).events.click();
  assert.ok(nodes.some(n => n.textContent === focusLabel('ok')));
  card.dispose();
});

test('画像ごとの生成文は出さず、訂正は直したい箇所と残したい箇所だけ送る', async () => {
  const calls = [];
  API.savePreviewReview = async () => { throw new Error('判定保存が呼ばれた'); };
  API.correctPreviewInterpretation = async (name, job, image, correction) => {
    calls.push({ name, job, image, ...correction });
    return { rating: 'ng', comment: '髪型が違う。衣装は合っている', focus: [], revision: 2, history: [],
      meaning: correction.meaning, meaning_source: 'user' };
  };
  const card = previewReviewCard('probe', 'job-a', {
    id: 'image-a', path: '/image-a.png',
    review: { rating: 'ng', comment: '髪型が違う。衣装は合っている', focus: [], revision: 1, history: [],
      meaning: { fix: ['髪型'], preserve: ['衣装'], questions: [], description_en: '1girl, twintails' }, meaning_source: 'ai' },
  }, 0, () => {});
  const nodes = all(card.node);
  const textareas = nodes.filter(n => n.tag === 'textarea');
  assert.equal(textareas[0].value, '髪型が違う。衣装は合っている');
  assert.ok(!nodes.some(n => n.children.includes('生成文（英語）')));
  assert.ok(!nodes.some(n => n.children.includes('生成文の詳細')));
  const correct = nodes.find(n => n.children.includes('この内容に訂正する'));
  await correct.events.click({ currentTarget: correct });
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].meaning, { fix: ['髪型'], preserve: ['衣装'], questions: [], description_en: '' });
  card.dispose();
});

test('OKの要約は維持だけ出し、保存済みのfixを画面から隠す', () => {
  const meaning = { fix: ['髪型', '顔'], preserve: ['衣装', 'スタイル', '体格比例', '背景'], questions: [], description_en: 'x' };
  assert.equal(meaningSummary('ok', meaning), '維持：衣装、スタイル、体格比例、背景');
  assert.equal(meaningSummary('ng', meaning), '修正：髪型、顔／維持：衣装、スタイル、体格比例、背景');
});

test('OKカードは保存済みの直したい箇所を出さず、訂正も残したい欄だけ', () => {
  const card = previewReviewCard('probe', 'job-a', {
    id: 'image-a', path: '/image-a.png',
    review: {
      rating: 'ok', comment: '', focus: ['hair', 'face', 'outfit', 'body', 'style'], revision: 1, history: [],
      meaning: { fix: ['髪型', '顔'], preserve: ['衣装', 'スタイル', '体格比例', '背景'], questions: [], description_en: '1girl' },
      meaning_source: 'ai',
    },
  }, 0, () => {});
  const texts = strings(card.node);
  const nodes = all(card.node);
  assert.ok(!texts.some(t => t.includes('直したい箇所')));
  assert.ok(!texts.some(t => t.includes('髪型')));
  assert.ok(texts.some(t => t.includes('残したい箇所') && t.includes('衣装')));
  assert.ok(!nodes.some(n => n.children.includes('生成文（英語）')));
  assert.ok(!nodes.some(n => n.children.includes('直したい箇所')));
  assert.ok(!nodes.some(n => n.children.includes('null')));
  card.dispose();
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { API } from '../web/api.js';

test('preview sends the selected style, including Japanese names', async (t) => {
  let request;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    request = { url: new URL(url, 'http://test'), options };
    return { ok: true, json: async () => ({ pictures: [] }) };
  });
  await API.previewCharacter('ベル', 'waving', 7, 2, '水彩');
  assert.equal(request.url.pathname, '/api/characters/%E3%83%99%E3%83%AB/preview');
  assert.equal(request.url.searchParams.get('style'), '水彩');
  assert.equal(request.url.searchParams.get('seed'), '7');
  assert.equal(request.url.searchParams.get('count'), '2');
  assert.equal(request.options.method, 'POST');
  await API.previewCharacter('Bell', 'standing');
  assert.equal(request.url.searchParams.get('style'), '');
});

test('注文の原文と確認内容をJSONで送り、画像順を保つ', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url, options });
    return { ok: true, json: async () => ({ job_id: 'intent-1' }) };
  });
  const request = { name: 'ベル', kind: 'character', stage: 'samples', comment: '  4枚目を使って\n', sample_indices: [3, 0, 2, 1] };
  await API.saveComment(request);
  assert.deepEqual(JSON.parse(calls[0].options.body), request);
  assert.equal(calls[0].options.headers['Content-Type'], 'application/json');
  await API.interpretComment('intent-1');
  assert.equal(calls[1].url, '/api/intents/intent-1/interpret');
  const proposal = { changes: [], observations: [], questions: [] };
  await API.confirmComment('intent-1', proposal);
  assert.deepEqual(JSON.parse(calls[2].options.body), proposal);
  await API.previewCharacter('ベル', '', 1, 2, '', 'intent-1');
  assert.equal(new URL(calls[3].url, 'http://test').searchParams.get('intent_job_id'), 'intent-1');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { API } from '../web/api.js';

test('描き直しの一覧は対象キャラクターの完成済み構成を指定する', async t => {
  let url;
  t.mock.method(globalThis, 'fetch', async value => {
    url = new URL(value, 'http://test');
    return {ok:true,json:async()=>[]};
  });
  await API.panels('ベル', true);
  assert.equal(url.searchParams.get('name'), 'ベル');
  assert.equal(url.searchParams.get('generated'), 'true');
  await API.panels();
  assert.equal(url.pathname, '/api/panels');
  assert.equal(url.search, '');
});

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

test('教材の表示では学習を呼ばず、開始時は表示済みjobを指定する', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({url:new URL(url,'http://test'),options});
    return {ok:true,json:async()=>({job_id:'prepared'})};
  });
  await API.prepareTraining('ベル','character',30);
  assert.equal(calls[0].url.pathname,'/api/training/prepare');
  assert.equal(calls.length,1);
  await API.train('ベル',30,'prepared');
  assert.equal(calls[1].url.searchParams.get('prepared_job_id'),'prepared');
  const observations = [{caption_en:'white jacket'}];
  await API.confirmObservations('intent',observations);
  assert.deepEqual(JSON.parse(calls[2].options.body),observations);
});

test('一枚生成の両経路へ確定した注文と選択した画風を送る', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({url:new URL(url,'http://test'),options});
    return {ok:true,json:async()=>({job_id:'drawing'})};
  });
  await API.fromBible('ベル','',7,'水彩','character-order');
  await API.image('','水彩',8,'style-order');
  assert.equal(calls[0].url.pathname,'/api/from-bible');
  assert.equal(calls[0].url.searchParams.get('intent_job_id'),'character-order');
  assert.equal(calls[0].url.searchParams.get('style'),'水彩');
  assert.equal(calls[1].url.pathname,'/api/image');
  assert.equal(calls[1].url.searchParams.get('intent_job_id'),'style-order');
  assert.equal(calls[1].url.searchParams.get('prompt'),'');
  assert.equal(calls[1].options.method,'POST');
});

test('設定画とパネル修正へ採用した注文を送る', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async url => {
    calls.push(new URL(url, 'http://test'));
    return {ok:true,json:async()=>({})};
  });
  await API.bible('ベル',5,'水彩','sheet-order');
  await API.redraw('ベル','item_shoes','',9,'','panel-order','intent');
  assert.equal(calls[0].searchParams.get('intent_job_id'),'sheet-order');
  assert.equal(calls[0].searchParams.get('style'),'水彩');
  assert.equal(calls[1].searchParams.get('intent_job_id'),'panel-order');
  assert.equal(calls[1].searchParams.get('panel'),'item_shoes');
  assert.equal(calls[1].searchParams.get('tags'),'');
  assert.equal(calls[1].searchParams.get('input_mode'),'intent');
  await API.redraw('ベル','item_shoes','green boots',9,'','','english');
  assert.equal(calls[2].searchParams.get('input_mode'),'english');
  assert.equal(calls[2].searchParams.get('tags'),'green boots');
});

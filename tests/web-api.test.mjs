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

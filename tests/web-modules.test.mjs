import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { basename, join } from 'node:path';

// './jobs.js?v=1' と './jobs.js?v=2' はブラウザーにとって別のモジュールになり、
// 同じファイルが二重に読み込まれて状態が分裂する。参照は素のパスだけに保つ。
const query = /['"]([\w./-]+\.(?:js|mjs|css))\?([^'"\s]*)['"]/g;
const self = basename(fileURLToPath(import.meta.url));

function queried(dir, names) {
  const found = [];
  for (const name of names) {
    const text = readFileSync(join(dir, name), 'utf8');
    for (const [, path, search] of text.matchAll(query)) found.push(`${name}: ${path}?${search}`);
  }
  return found;
}

test('WebUI の参照にクエリ文字列を付けない', () => {
  const dir = fileURLToPath(new URL('../web/', import.meta.url));
  const names = readdirSync(dir).filter(name => /\.(js|css|html)$/.test(name));
  assert.ok(names.includes('main.js'), '走査対象が空でないこと');
  assert.deepEqual(queried(dir, names), []);
});

test('WebUI を読む試験の参照にもクエリ文字列を付けない', () => {
  const dir = fileURLToPath(new URL('./', import.meta.url));
  // 本書は検出できることを示す例文を持つため、走査からは外す。
  const names = readdirSync(dir).filter(name => name.endsWith('.mjs') && name !== self);
  assert.ok(names.includes('web-flow.test.mjs'), '走査対象が空でないこと');
  assert.deepEqual(queried(dir, names), []);
});

test('クエリ付きの参照は検出できる', () => {
  const [hit] = [...`import { API } from './api.js?v=studio-4';`.matchAll(query)];
  assert.deepEqual([hit[1], hit[2]], ['./api.js', 'v=studio-4']);
});

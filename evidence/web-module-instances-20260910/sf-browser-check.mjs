import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';

const require = createRequire('/Users/kite/Developer/blog-figmaker/package.json');
const { chromium } = require('playwright');

const BASE = process.env.SF_BASE || 'http://192.168.1.2:8766';
const SHOT = '/tmp/sf-shots';
mkdirSync(SHOT, { recursive: true });

const MODULES = ['main.js', 'flows.js', 'jobs.js', 'api.js', 'intent.js', 'learning.js', 'preview.js', 'layout.js', 'strength.js', 'training.js', 'ui.js', 'drafts.js', 'state.js', 'style.css'];
const report = { base: BASE, screens: [], findings: {} };

function tally(urls) {
  const counts = {};
  for (const url of urls) {
    const name = new URL(url).pathname.replace(/^\//, '');
    if (MODULES.includes(name)) counts[name] = (counts[name] || 0) + 1;
  }
  return counts;
}

async function visit(page, hash, label, tag) {
  await page.goto(`${BASE}/#/${hash}`, { waitUntil: 'load' });
  await page.waitForTimeout(1200);
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    wide: [...document.querySelectorAll('*')].filter(el => el.getBoundingClientRect().right > window.innerWidth + 1).map(el => `${el.tagName.toLowerCase()}.${el.className || ''}`).slice(0, 5),
  }));
  const shot = `${SHOT}/${tag}-${label}.png`;
  await page.screenshot({ path: shot, fullPage: false });
  return { hash, label, tag, overflow, shot };
}

const browser = await chromium.launch();

// --- 1. デスクトップ幅: 全画面を回り、モジュールの読み込み回数とエラーを数える ---
{
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const requests = [];
  const errors = [];
  page.on('request', r => requests.push(r.url()));
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });

  report.screens.push(await visit(page, '', 'studio', 'desktop'));
  const flows = await page.$$eval('a.flow-tile', els => els.map(el => el.getAttribute('href').replace(/^#\//, '')));
  report.findings.flows = flows;
  for (const id of ['library', 'activity', 'tools', ...flows]) {
    report.screens.push(await visit(page, id, id.replace(/\//g, '-'), 'desktop'));
  }

  report.findings.moduleLoads = tally(requests);
  report.findings.queryStringRefs = requests.filter(u => /\.(js|mjs|css)\?/.test(u));
  report.findings.consoleErrors = errors;

  // --- 2. 別インスタンスの対照実験 ---
  // 素のパスで読むと main.js と同じインスタンスになり、main.js が回している
  // 2.5秒ごとの追跡の emit が届く。版番号付きで読むと別インスタンスになり、届かない。
  await page.goto(`${BASE}/#/activity`, { waitUntil: 'load' });
  await page.waitForTimeout(500);
  const ab = await page.evaluate(async () => {
    const plain = await import('/jobs.js');
    const tagged = await import('/jobs.js?v=studio-4');
    const hits = { plain: -1, tagged: -1 }; // subscribe は登録時に1回呼ぶので -1 から数える
    plain.subscribe(() => hits.plain++);
    tagged.subscribe(() => hits.tagged++);
    const sameInstance = plain.operations === tagged.operations;
    await new Promise(r => setTimeout(r, 7000));
    return { ...hits, sameInstance };
  });
  report.findings.crossIsland = ab;

  // 追跡そのものが動いているか（/api/jobs の呼び出し回数）
  const jobCalls = requests.filter(u => u.endsWith('/api/jobs')).length;
  report.findings.apiJobsCalls = jobCalls;
  await context.close();
}

// --- 3. スマホ幅 ---
{
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  for (const id of ['', 'library', 'activity', 'tools', ...report.findings.flows]) {
    report.screens.push(await visit(page, id, id.replace(/\//g, '-') || 'studio', 'phone'));
  }
  report.findings.phoneConsoleErrors = errors;
  await context.close();
}

await browser.close();

const overflowing = report.screens.filter(s => s.overflow.scrollWidth > s.overflow.innerWidth + 1);
report.findings.overflowingScreens = overflowing.map(s => ({ tag: s.tag, label: s.label, scrollWidth: s.overflow.scrollWidth, innerWidth: s.overflow.innerWidth, wide: s.overflow.wide }));

writeFileSync('/tmp/sf-browser-report.json', JSON.stringify(report, null, 2));

const dup = Object.entries(report.findings.moduleLoads).filter(([, n]) => n !== 1);
console.log('=== モジュール読み込み回数 ===');
console.log(JSON.stringify(report.findings.moduleLoads));
console.log('1回以外のもの:', dup.length ? JSON.stringify(dup) : 'なし');
console.log('クエリ付き参照:', report.findings.queryStringRefs.length, '件');
console.log('=== 対照実験（7秒間の emit 受信回数） ===');
console.log('素のパスで読んだ jobs.js:', report.findings.crossIsland.plain);
console.log('版番号付きで読んだ jobs.js:', report.findings.crossIsland.tagged);
console.log('同一インスタンスか:', report.findings.crossIsland.sameInstance);
console.log('/api/jobs 呼び出し:', report.findings.apiJobsCalls, '回');
console.log('=== 画面 ===');
console.log('訪問:', report.screens.length, '画面（flow:', report.findings.flows.join(', '), '）');
console.log('横あふれ:', report.findings.overflowingScreens.length ? JSON.stringify(report.findings.overflowingScreens) : 'なし');
console.log('コンソールエラー(desktop):', report.findings.consoleErrors.length ? report.findings.consoleErrors : 'なし');
console.log('コンソールエラー(phone):', report.findings.phoneConsoleErrors.length ? report.findings.phoneConsoleErrors : 'なし');

import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';

const require = createRequire('/Users/kite/Developer/blog-figmaker/package.json');
const { chromium } = require('playwright');

const base = 'http://192.168.1.2:8766';
const browser = await chromium.launch();

async function look(label, viewport) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const problems = [];
  page.on('pageerror', error => problems.push(`pageerror: ${error.message}`));
  page.on('console', message => { if (message.type() === 'error') problems.push(`console: ${message.text()}`); });

  await page.goto(`${base}/#/flow/sheet`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(2500);

  const text = await page.locator('body').innerText();
  const shot = `/tmp/sf-verify-${label}.png`;
  await page.screenshot({ path: shot, fullPage: true });

  const heading = await page.locator('h1, h2, h3').allInnerTexts();
  const overflow = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return [...document.querySelectorAll('*')].filter(el => el.getBoundingClientRect().right > width + 1).length;
  });
  await context.close();
  return {
    label,
    エラー表示: text.includes('読み込めませんでした'),
    approved_sheetのエラー: text.includes("approved_sheet"),
    工程の見出し: heading.slice(0, 4),
    未選択の案内: text.includes('選ぶか、新しく登録してください。'),
    横あふれ: overflow,
    コンソール異常: problems,
    画像: shot,
  };
}

const report = [await look('desktop', { width: 1440, height: 900 }), await look('phone', { width: 390, height: 844 })];
await browser.close();
console.log(JSON.stringify(report, null, 2));
writeFileSync('/tmp/sf-verify-sheet.json', JSON.stringify(report, null, 2));

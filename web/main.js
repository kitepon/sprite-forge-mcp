import { API } from './api.js?v=studio-2';
import { h, $, icon, button, link, field, picture, empty, notice, action, pageHead, errorState, dateText } from './ui.js?v=studio-2';
import { FLOWS, flow, cover, openFlow } from './flows.js?v=studio-2';
import { jobs, operations, active, connectionError, subscribe, refreshJobs, startJobUpdates, tickElapsed, terminal, kindLabel, imagePaths, jobView, taskPanel } from './jobs.js?v=studio-2';
import { draft, saveDraft } from './drafts.js?v=studio-2';

const routes = [{ id: '', label: 'スタジオ', icon: 'home' }, { id: 'library', label: '作品と素材', icon: 'grid' }, { id: 'activity', label: '制作状況', icon: 'activity' }, { id: 'tools', label: '道具箱', icon: 'tool' }];
let dispose = () => {}; let routeVersion = 0;
function flowTile(spec, index) {
  return h('a', { href: `#/flow/${spec.id}`, class: `flow-tile flow-${spec.id}` }, h('div', { class: 'flow-tile-top' }, h('span', { class: 'flow-icon' }, icon(spec.icon, 25)), h('span', { class: 'flow-number' }, `0${index + 1}`)), h('h3', {}, spec.title), h('p', {}, spec.desc), h('span', { class: 'flow-bottom' }, h('span', {}, `${spec.steps.length} ステップ`), icon('arrow')));
}
async function home(root) {
  const [characters, styles, history] = await Promise.all([API.characters(), API.styles(), API.jobs()]);
  const first = characters.find(rec => rec.samples.length) || characters[0];
  const heroImages = first?.samples?.slice(0, 3) || [];
  const art = h('div', { class: `hero-art ${heroImages.length ? '' : 'no-art'}`, 'aria-label': first ? `${first.name}の参考画像` : '制作スタジオ' }, h('span', { class: 'hero-orbit' }), h('span', { class: 'hero-star star-one' }, '✦'), h('span', { class: 'hero-star star-two' }, '✳'),
    heroImages.length ? heroImages.map((sample, index) => h('div', { class: `art-print print-${index}` }, picture(sample.path, `${first.name}の参考画像 ${index + 1}`), h('span', { class: 'print-caption' }, index === 0 ? first.name : ['REFERENCE', 'EXPRESSION', 'CHARACTER'][index]))) : h('div', { class: 'blank-canvas' }, icon('spark', 70), h('span', {}, 'Your character,', h('br'), 'your world.')),
    h('span', { class: 'hero-sticker' }, icon('check', 16), 'ひとつずつ、あなたらしく'));
  root.replaceChildren(h('section', { class: 'hero' }, h('div', { class: 'hero-copy' }, h('p', { class: 'eyebrow' }, h('span', { class: 'tiny-dot' }), 'LET’S MAKE SOMETHING YOURS'), h('h1', {}, 'そのキャラの、', h('br'), h('span', {}, '次の一枚を。')), h('p', { class: 'hero-description' }, '好きな画像を集めて、らしさを覚えて。', h('br'), '確かめながら、少しずつ形にしていこう。'), link(['キャラクターを作る', icon('arrow')], '#/flow/sheet', 'button-link hero-cta'), h('p', { class: 'hero-footnote' }, '途中からでも、何度戻っても。')), art),
    h('section', { class: 'section stack' }, h('div', { class: 'section-heading' }, h('div', {}, h('p', { class: 'eyebrow' }, 'CHOOSE YOUR NEXT STEP'), h('h2', {}, '今日は、何を作ろう。')), h('span', { class: 'muted small' }, '目的に合わせて、5 つのコース')), h('div', { class: 'flow-cards' }, FLOWS.map(flowTile))),
    h('section', { class: 'section stack' }, h('div', { class: 'section-heading' }, h('div', {}, h('p', { class: 'eyebrow' }, 'YOUR CHARACTERS'), h('h2', {}, '制作の続きを')), link(['すべて見る', icon('arrow', 17)], '#/library?tab=characters', 'text-link')),
      characters.length ? h('div', { class: 'home-characters' }, characters.slice(0, 4).map(rec => h('article', { class: 'continue-card' }, h('div', { class: 'continue-cover' }, picture(cover(rec), rec.name)), h('div', { class: 'stack' }, h('div', { class: 'section-heading' }, h('h3', {}, rec.name), h('span', { class: `badge ${rec.lora_name ? 'green' : ''}` }, rec.lora_name ? '学習済み' : '準備中')), h('p', { class: 'muted small' }, `${rec.samples.length} 枚の参考画像${rec.bible ? ' · 設定画あり' : ''}`), button(['続きを作る', icon('arrow', 16)], () => openFlow('sheet', rec.name, 'character', rec.bible ? 4 : rec.lora_name ? 3 : 1), 'quiet'))))) : empty('あなたのキャラクターが、ここに並びます', 'まずは気に入った画像から始めてみましょう。', link([icon('plus'), '最初のキャラクター'], '#/flow/sheet'))),
    h('div', { class: 'studio-footer' }, h('span', {}, `${characters.length} キャラクター`), h('span', {}, `${styles.length} 画風`), h('span', {}, `${history.filter(job => job.status === 'completed' && imagePaths(job).length).length} 件の制作`)));
}

async function library(root, query, cleanup) {
  const [characters, styles] = await Promise.all([API.characters(), API.styles()]);
  await refreshJobs(); let tab = query.get('tab') || 'works';
  const search = h('input', { type: 'search', placeholder: '名前や描いた内容で探す', 'aria-label': '作品と素材を検索' });
  const tabs = h('div', { class: 'tabs', role: 'tablist', 'aria-label': '表示するコレクション' }); const content = h('div', { class: 'gallery', role: 'tabpanel' }); const count = h('span', { class: 'muted small' });
  const render = () => {
    tabs.replaceChildren(...[['works', 'できた作品'], ['characters', 'キャラクター'], ['styles', '画風']].map(([key, label]) => h('button', { type: 'button', class: tab === key ? 'active' : '', role: 'tab', 'aria-selected': String(tab === key), onclick: () => { tab = key; render(); } }, label)));
    const term = search.value.toLowerCase();
    if (tab === 'works') {
      const filtered = jobs.filter(job => imagePaths(job).length && `${job.name || ''} ${job.style || ''} ${job.prompt || ''} ${kindLabel(job.kind)}`.toLowerCase().includes(term));
      const works = filtered.flatMap(job => imagePaths(job).map((path, index) => ({ job, path, index })));
      count.textContent = `${works.length} 枚`;
      content.replaceChildren(...works.map(({ job, path, index }) => h('article', { class: 'work-card' }, picture(path, `${job.name || job.style || kindLabel(job.kind)} ${index + 1}`, { version: job.updated_at || job.job_id }), h('div', { class: 'work-caption' }, h('div', { class: 'section-heading' }, h('span', { class: 'badge' }, kindLabel(job.kind)), h('small', { class: 'muted' }, job.status === 'completed' ? '完成' : '途中の画像')), h('h3', {}, job.name || job.style || '新しい一枚'), h('p', { class: 'muted small' }, dateText(job.created_at)), h('div', { class: 'actions' }, button('詳しく見る', () => showWork(job, index), 'text-button'), button('道具箱で使う', () => { saveDraft('tools:source', path); location.hash = '#/tools'; }, 'text-button'))))));
    } else {
      const kind = tab === 'characters' ? 'character' : 'style'; const items = (kind === 'character' ? characters : styles).filter(rec => rec.name.toLowerCase().includes(term)); count.textContent = `${items.length} 件`;
      content.replaceChildren(...items.map(rec => h('article', { class: 'work-card entity-record' }, picture(cover(rec), rec.name), h('div', { class: 'work-caption stack' }, h('div', { class: 'section-heading' }, h('h3', {}, rec.name), h('span', { class: `badge ${rec.lora_name ? 'green' : ''}` }, rec.lora_name ? '学習済み' : '未学習')), h('p', { class: 'muted small' }, `${rec.samples.length} 枚の参考画像`), h('div', { class: 'actions' }, button('参考画像を編集', () => openFlow(kind === 'character' ? 'sheet' : 'style', rec.name, kind, 1), 'quiet small-button'), rec.lora_name ? button('この子で描く'.replace('この子', kind === 'style' ? 'この画風' : 'この子'), () => openFlow(kind === 'character' ? 'draw' : 'styleonly', rec.name, kind, 1), 'text-button') : null), rec.bible ? button('設定画を見る・直す', () => openFlow('sheet', rec.name, 'character', 4), 'text-button') : null))));
    }
    if (!content.childElementCount) content.append(empty(search.value ? '見つかりませんでした' : 'ここに作品が並びます', search.value ? '別の名前や言葉で探してみてください。' : 'コースから制作を始めると、作品も素材もここで見返せます。', link('スタジオへ', '#/')));
  };
  search.addEventListener('input', render);
  root.replaceChildren(pageHead('YOUR COLLECTION', '作品と素材', 'できた絵も、集めた画像も。次の一枚に使いましょう。', link([icon('plus'), '新しく作る'], '#/')), h('div', { class: 'library-toolbar' }, tabs, search), h('div', { class: 'section-heading' }, count), content);
  let signature = ''; cleanup.push(subscribe(() => { const next = JSON.stringify(jobs.map(job => [job.job_id, job.updated_at, job.status])); if (signature !== next) { signature = next; render(); } })); render();
}
function showWork(job, index) {
  const dialog = h('dialog', { class: 'work-dialog', 'aria-label': '作品の詳細' }); const close = button(icon('close'), () => dialog.close(), 'icon-button'); close.setAttribute('aria-label', '詳細を閉じる');
  dialog.append(h('div', { class: 'section-heading' }, h('h2', {}, job.name || job.style || kindLabel(job.kind)), close), picture(imagePaths(job)[index], '作品', { version: job.updated_at || job.job_id }), h('p', { class: 'muted' }, kindLabel(job.kind)), job.prompt ? h('div', { class: 'callout' }, h('strong', {}, '描いた内容'), h('p', {}, job.prompt)) : null, h('p', { class: 'muted small' }, `Seed: ${job.seed ?? '記録なし'} · ${dateText(job.created_at)}`), link([icon('download'), '画像を保存'], API.file(imagePaths(job)[index])));
  dialog.addEventListener('close', () => dialog.remove()); document.body.append(dialog); dialog.showModal();
}
function activity(root, cleanup) {
  const content = h('div', { class: 'activity-list stack' }); const stateLabel = h('p', { class: 'muted small' });
  const filter = h('select', { 'aria-label': '制作状況の絞り込み' }, h('option', { value: 'active' }, '未完了・応答待ち'), h('option', { value: 'all' }, 'すべて'), h('option', { value: 'failed' }, '失敗した処理'), h('option', { value: 'completed' }, '完了した処理'));
  const render = () => {
    stateLabel.textContent = connectionError ? `接続を確認できません。最後に取得した状態を表示中: ${connectionError}` : '2.5 秒ごとに記録を確認しています。更新日時は最後の報告時刻です。';
    const unsent = [...operations.values()].filter(op => !op.job && (op.requesting || op.error));
    const filtered = jobs.filter(job => filter.value === 'all' || (filter.value === 'active' ? !terminal(job) : filter.value === 'completed' ? ['completed','success'].includes(job.status) : ['failed','error'].includes(job.status)));
    content.replaceChildren(...(filter.value === 'active' || filter.value === 'all' ? unsent.map(op => jobView(null, op)) : []), ...filtered.map(job => {
      const op = [...operations.values()].find(value => value.job?.job_id === job.job_id);
      return jobView(job, { startedAt: op?.startedAt || job.created_at, error: op?.error });
    }));
    if (!content.childElementCount) content.append(empty(filter.value === 'active' ? 'いま、未完了の制作はありません' : '該当する記録はありません', 'できた画像は「作品と素材」で見返せます。', link('作品と素材へ', '#/library')));
    tickElapsed(content);
  };
  root.replaceChildren(pageHead('IN THE MAKING', '制作状況', '待っている間も、描けたところから。', filter), stateLabel, content);
  let signature = ''; cleanup.push(subscribe(() => { const next = JSON.stringify([jobs, [...operations], connectionError]); if (next !== signature) { signature = next; render(); } })); filter.addEventListener('change', render); render();
}
async function toolsPage(root, cleanup) {
  const sourceView = h('div', { class: 'source-preview' }); let source = draft('tools:source', ''); const finish = h('div', { class: 'stack' }); let finishCleanup = [];
  const setSource = path => {
    source = path; saveDraft('tools:source', source); sourceView.replaceChildren(source ? picture(source, '加工する画像') : empty('加工する画像を選んでください', '作品から選ぶか、画像をアップロードできます。'));
    finishCleanup.forEach(fn => fn()); finishCleanup = [];
    finish.replaceChildren(...(source ? [taskPanel({ kind: 'transparent', source }, '背景の透過', '背景を透過する', () => API.transparent(source), finishCleanup), taskPanel({ kind: 'pixelize', source }, 'ドットへの変換', 'ドットに整える', () => API.pixelize(source), finishCleanup)] : []));
  };
  cleanup.push(() => finishCleanup.forEach(fn => fn()));
  const upload = h('input', { type: 'file', accept: 'image/*', 'aria-label': '加工する画像をアップロード', onchange: event => action(event.currentTarget, async () => { if (!upload.files.length) return; setSource((await API.upload(upload.files))[0].path); notice('加工する画像を読み込みました'); }) });
  const prompt = h('textarea', { rows: 4, placeholder: '例：a small forest mage, standing, full body', oninput: event => saveDraft('tools:prompt', event.target.value) }, draft('tools:prompt'));
  const seed = h('input', { type: 'number', min: 0, step: 1, value: draft('tools:seed', '1'), oninput: event => saveDraft('tools:seed', event.target.value) });
  root.replaceChildren(pageHead('A LITTLE FINISHING TOUCH', '道具箱', '新しいスプライトを作ったり、できた画像を整えたり。'), h('div', { class: 'tools-layout' }, h('section', { class: 'card stack' }, h('span', { class: 'flow-icon' }, icon('spark')), h('h2', {}, 'スプライトを描く'), h('p', { class: 'muted' }, '言葉から画像を生成し、背景を透過します。キャラクターや画風を使う制作は、スタジオのコースから。'), field('描きたい内容', prompt), h('details', { class: 'advanced' }, h('summary', {}, '詳細設定'), field('Seed', seed)), taskPanel({ kind: 'sprite' }, 'スプライト', 'スプライトを作る', () => { if (!prompt.value.trim()) throw new Error('描きたい内容を入力してください。'); if (!seed.reportValidity()) throw new Error('Seed を確認してください。'); return API.sprite(prompt.value, seed.value); }, cleanup, job => { if (imagePaths(job)[0]) setSource(imagePaths(job)[0]); })), h('section', { class: 'card stack' }, h('span', { class: 'flow-icon peach' }, icon('tool')), h('h2', {}, '画像を仕上げる'), sourceView, h('div', { class: 'stack' }, field('画像をアップロード', upload), link('作品から選ぶ', '#/library', 'text-link')), finish)));
  setSource(source);
}
async function route() {
  dispose(); const cleanup = []; dispose = () => cleanup.splice(0).forEach(fn => fn()); const current = ++routeVersion;
  const [path = '', search = ''] = location.hash.replace(/^#\/?/, '').split('?');
  const aliases = { records: 'library', process: 'activity', workbench: 'tools', settings: 'flow/sheet', lora: 'flow/sheet' };
  if (aliases[path]) { location.hash = `#/${aliases[path]}`; return; }
  const page = routes.find(item => item.id === path) || routes[0];
  document.title = `${path.startsWith('flow/') ? FLOWS.find(f => f.id === path.split('/')[1])?.title || '制作' : page.label} — Sprite Forge`;
  $('#breadcrumb').textContent = path.startsWith('flow/') ? 'スタジオ / 制作コース' : page.label;
  $('#nav').replaceChildren(...routes.map(item => h('a', { href: `#/${item.id}`, class: page.id === item.id ? 'active' : '', 'aria-current': page.id === item.id ? 'page' : null }, icon(item.icon), h('span', {}, item.label))));
  const root = h('div', { class: 'page' }); $('#app').replaceChildren(root); window.scrollTo(0, 0);
  if (path.startsWith('flow/')) { cleanup.push(flow(root, path.split('/')[1])); return; }
  root.append(h('div', { class: 'loading-placeholder' }, h('span', { class: 'working' }, icon('spark', 30)), 'スタジオを開いています…'));
  try {
    if (path === 'library') await library(root, new URLSearchParams(search), cleanup);
    else if (path === 'activity') activity(root, cleanup);
    else if (path === 'tools') await toolsPage(root, cleanup);
    else await home(root);
  } catch (error) { if (current === routeVersion) errorState(root, error); }
  if (current !== routeVersion) cleanup.splice(0).forEach(fn => fn());
}
async function gpu() {
  try { const info = await API.gpu(); const online = info.online !== false && !info.error;
    $('#gpu').textContent = online ? 'GPU 接続済み' : 'GPU に接続できません'; $('#gpu-dot').className = `status-dot ${online ? 'online' : 'offline'}`;
  } catch { $('#gpu').textContent = 'GPU に接続できません'; $('#gpu-dot').className = 'status-dot offline'; }
}
subscribe(() => {
  const count = [...operations.values()].filter(active).length;
  $('#live-status').replaceChildren(h('span', { class: `status-dot ${connectionError ? 'offline' : count ? 'online' : ''}` }), connectionError ? '接続を確認中' : count ? `${count} 件を制作中` : '制作状況', icon('arrow', 15));
});
$('.skip-link').addEventListener('click', event => { event.preventDefault(); $('#app').focus(); });
window.addEventListener('hashchange', route); startJobUpdates(); setInterval(tickElapsed, 1000); gpu(); setInterval(gpu, 30000); route();

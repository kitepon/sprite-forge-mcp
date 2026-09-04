import { API } from './api.js?v=studio-2';
import { state } from './state.js?v=studio-2';
import { h, icon, field, button, link, picture, empty, notice, action, pageHead, errorState, confirmAction } from './ui.js?v=studio-2';
import { taskPanel } from './jobs.js?v=studio-2';
import { draft, saveDraft, clearDraft, pendingFiles } from './drafts.js?v=studio-2';

export const FLOWS = [
  { id: 'sheet', title: 'キャラクターを育てる', desc: '参考画像から、その子らしい設定画へ。', icon: 'layers', steps: ['キャラクター', '参考画像', '学習', 'プレビュー', '設定画'] },
  { id: 'draw', title: '新しい一枚を描く', desc: 'あのキャラクターを、まだ見ぬ場面に。', icon: 'spark', steps: ['キャラクター', '描く'] },
  { id: 'restyle', title: '画風を着せかえる', desc: '同じキャラクターに、違う絵の表情を。', icon: 'palette', steps: ['キャラクター', '画風', 'プレビュー', '設定画'] },
  { id: 'style', title: '好きな画風を覚える', desc: '線や色づかいを、次の制作にも。', icon: 'image', steps: ['画風', '参考画像', '学習', '試し描き'] },
  { id: 'styleonly', title: '画風から自由に描く', desc: '覚えた画風で、被写体は自由に。', icon: 'tool', steps: ['画風', '描く'] },
];
export function openFlow(id, name, kind = 'character', step = 0) {
  state.flow[kind] = name; state.flow.step = { ...state.flow.step, [id]: step }; state.saveFlow();
  if (location.hash === `#/flow/${id}`) window.dispatchEvent(new HashChangeEvent('hashchange'));
  else location.hash = `#/flow/${id}`;
}
export const cover = rec => rec.samples?.[0]?.path || rec.bible?.sheet_path;
export function entityTile(rec, selected, onPick) {
  return button([h('div', { class: 'entity-cover' }, picture(cover(rec), rec.name, { plain: true })), h('span', { class: 'entity-caption' }, h('strong', {}, rec.name), h('span', { class: 'muted small' }, `${rec.samples?.length || 0} 枚の参考画像`)), h('span', { class: `badge ${rec.lora_name ? 'green' : ''}` }, rec.lora_name ? '学習済み' : '準備中'), selected ? h('span', { class: 'selection-check' }, icon('check', 17)) : null], onPick, `entity-tile ${selected ? 'selected' : ''}`);
}
function input(key, value = '', attrs = {}) {
  return h(attrs.multiline ? 'textarea' : 'input', { ...attrs, value: attrs.multiline ? null : draft(key, value), oninput: e => saveDraft(key, e.target.value) }, attrs.multiline ? draft(key, value) : null);
}
function advanced(...children) { return h('details', { class: 'advanced' }, h('summary', {}, '詳細設定'), h('div', { class: 'form-grid' }, children)); }
function seedControl(key) { return input(`${key}:seed`, '1', { type: 'number', min: 0, step: 1 }); }
function requireText(control, label) { if (!control.value.trim()) { control.focus(); throw new Error(`${label}を入力してください。`); } return control.value.trim(); }
function number(control) { if (!control.reportValidity()) throw new Error('数値の入力を確認してください。'); return Number(control.value); }

async function choose(target, kind, ctx, createAllowed, changed) {
  const isChar = kind === 'character'; const noun = isChar ? 'キャラクター' : '画風';
  const items = await (isChar ? API.characters() : API.styles());
  const grid = h('div', { class: 'entity-grid' });
  const paint = () => grid.replaceChildren(...items.map(rec => {
    const tile = entityTile(rec, ctx[kind] === rec.name, () => { ctx[kind] = rec.name; state.saveFlow(); paint(); changed(); });
    tile.setAttribute('aria-pressed', String(ctx[kind] === rec.name)); return tile;
  })); paint();
  target.append(items.length ? grid : empty(`${noun}を登録しましょう`, createAllowed ? '名前を決めたら、参考にしたい画像を追加できます。' : '先に画像を集めて、学習を済ませてください。', !createAllowed ? link(`${noun}を作る`, `#/flow/${isChar ? 'sheet' : 'style'}`) : null));
  if (!createAllowed) return;
  const name = h('input', { required: true, placeholder: isChar ? '例：ベル' : '例：淡い水彩', autocomplete: 'off', maxlength: 100 });
  const desc = h('textarea', { rows: 3, placeholder: isChar ? '例：she/her, silver twin-tail idol, white and gold outfit' : 'どんな線や色づかいが好きですか？' });
  const trigger = h('input', { placeholder: '空欄なら自動で決めます' });
  const attr = h('input', { placeholder: '設定画に添える短いメモ' });
  const create = button([icon('plus'), `${noun}を登録`], e => action(e.currentTarget, async () => {
    const value = requireText(name, '名前');
    if (items.some(item => item.name === value)) throw new Error('同じ名前があるので、上のカードから選んでください。');
    const rec = await (isChar ? API.createCharacter(value, requireText(desc, 'キャラクターの説明'), attr.value, trigger.value) : API.createStyle(value, desc.value));
    items.push(rec); ctx[kind] = rec.name; state.saveFlow(); paint(); changed(); details.open = false; notice(`${rec.name}を登録しました。参考画像へ進めます。`);
  }));
  const details = h('details', { class: 'create-card', open: !items.length }, h('summary', {}, icon('plus'), `新しい${noun}を作る`), h('div', { class: 'stack' }, field('名前', name), field(isChar ? 'キャラクターの説明' : '画風のメモ', desc, isChar ? '本人の特徴・衣装・代名詞（she/her など）を英語で。画像ごとの説明は次の工程で書けます。' : ''), isChar ? advanced(field('呼び出し語', trigger), field('属性メモ', attr)) : null, create));
  target.append(details);
}

async function samples(target, kind, name, cleanup, changed) {
  const isChar = kind === 'character'; const key = `${kind}:${name}`;
  const load = () => isChar ? API.character(name) : API.style(name);
  const setCaption = isChar ? API.setCaption : API.setStyleCaption;
  const removeSample = isChar ? API.removeSample : API.removeStyleSample;
  const addSample = isChar ? API.addSamples : API.addStyleSamples;
  const list = h('div', { class: 'sample-grid' }); const count = h('span', { class: 'badge' });
  target.append(h('div', { class: 'section-heading' }, h('h3', {}, '集めた画像'), count), h('p', { class: 'muted' }, '一枚ごとに衣装や構図を書き分けます。4 枚以上を目安に、本人らしさが分かる画像を。'), list);
  const paint = rec => {
    count.textContent = `${rec.samples.length} 枚`;
    list.replaceChildren(...rec.samples.map((sample, index) => {
      const capKey = `${key}:caption:${sample.index}:${sample.path}`;
      const cap = h('textarea', { rows: 3, placeholder: 'この絵の衣装・ポーズ・構図など', 'aria-label': `画像 ${index + 1} の説明` }, draft(capKey, sample.caption || ''));
      const saved = h('span', { class: 'draft-status' }, cap.value !== (sample.caption || '') ? '未保存' : '保存済み');
      cap.addEventListener('input', () => { saveDraft(capKey, cap.value); saved.textContent = cap.value !== (sample.caption || '') ? '未保存' : '保存済み'; });
      const save = button('説明を保存', e => action(e.currentTarget, async () => {
        const value = cap.value; await setCaption(name, sample.index, value); sample.caption = value;
        if (cap.value === value) { clearDraft(capKey); saved.textContent = '保存済み'; } notice(`画像 ${index + 1} の説明を保存しました`);
      }), 'quiet small-button');
      const remove = button('外す', e => action(e.currentTarget, async () => {
        if (!await confirmAction(`画像 ${index + 1} を参考画像から外しますか？`)) return;
        const rec = await removeSample(name, sample.index); clearDraft(capKey); paint(rec); changed(rec); notice('参考画像から外しました。元のアップロード画像は残っています。');
      }), 'text-button danger');
      return h('article', { class: 'sample-card' }, picture(sample.path, `参考画像 ${index + 1}`), h('div', { class: 'sample-content stack' }, h('div', { class: 'section-heading' }, h('strong', {}, `画像 ${index + 1}`), saved), cap, h('div', { class: 'actions' }, save, remove)));
    }));
    if (!rec.samples.length) list.append(empty('まだ画像がありません', '下の枠から、最初の参考画像を選んでください。'));
  };
  paint(await load());
  if (!pendingFiles.has(key)) pendingFiles.set(key, []);
  const pending = pendingFiles.get(key);
  pending.listeners ||= new Set();
  const notifyPending = () => pending.listeners.forEach(fn => fn());
  const tray = h('div', { class: 'sample-grid pending-grid' });
  const label = h('span');
  const fileInput = h('input', { type: 'file', multiple: true, accept: 'image/*', class: 'sr-only', id: `sample-upload-${kind}`, onchange: () => { addFiles(fileInput.files); fileInput.value = ''; } });
  const drop = h('label', { class: 'dropzone', for: fileInput.id }, fileInput, h('span', { class: 'upload-symbol' }, icon('upload', 24)), h('strong', {}, '画像を選ぶ'), h('span', { class: 'muted small' }, '複数選択・ドラッグ＆ドロップに対応'));
  const addFiles = files => { if (pending.busy) return; for (const file of files) pending.push({ file, url: URL.createObjectURL(file), caption: '', status: '追加前' }); notifyPending(); };
  drop.addEventListener('dragover', event => { event.preventDefault(); drop.classList.add('dragging'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
  drop.addEventListener('drop', event => { event.preventDefault(); drop.classList.remove('dragging'); addFiles(event.dataTransfer.files); });
  const add = button([icon('plus'), '選んだ画像を追加'], e => action(e.currentTarget, async () => {
    if (!pending.length || pending.busy) return;
    pending.busy = true; notifyPending(); let added = 0;
    try {
      while (pending.length) {
        const item = pending[0];
        if (!item.path) { item.status = '転送中'; notifyPending(); item.path = (await API.upload([item.file]))[0].path; }
        item.status = '台帳へ追加中'; notifyPending();
        const rec = await addSample(name, item.path, item.caption);
        pending.shift(); URL.revokeObjectURL(item.url); added++; pending.latest = rec; notifyPending(); changed(rec);
      }
      notice(`${added} 枚を参考画像に追加しました`);
    } catch (error) {
      if (pending[0]) pending[0].status = '追加できませんでした';
      throw new Error(`${added} 枚は追加済みです。残りの画像: ${error.message}`);
    } finally { pending.busy = false; notifyPending(); }
  }));
  function renderPending() {
    label.textContent = pending.length ? `${pending.length} 枚を選択中 · まだ参考画像には追加されていません` : '';
    tray.replaceChildren(...pending.map((item, index) => {
      const cap = h('textarea', { rows: 2, disabled: pending.busy, 'aria-label': `${item.file.name} の説明`, placeholder: 'この画像の説明（任意）', oninput: event => { item.caption = event.target.value; } }, item.caption);
      return h('article', { class: 'sample-card pending' }, h('div', { class: 'picture' }, h('img', { src: item.url, alt: item.file.name })), h('div', { class: 'sample-content stack' }, h('strong', { class: 'truncate' }, item.file.name), h('small', { class: 'muted' }, item.status), cap, button('選択から外す', () => { if (pending.busy) return; pending.splice(index, 1); URL.revokeObjectURL(item.url); notifyPending(); }, 'text-button')));
    }));
    add.hidden = !pending.length; add.disabled = !!pending.busy; fileInput.disabled = !!pending.busy; drop.classList.toggle('uploading', !!pending.busy);
  }
  let lastRecord = pending.latest;
  const onPending = () => { if (pending.latest && pending.latest !== lastRecord) { lastRecord = pending.latest; paint(pending.latest); } renderPending(); };
  pending.listeners.add(onPending); cleanup.push(() => pending.listeners.delete(onPending));
  renderPending(); target.append(h('div', { class: 'upload-section stack' }, drop, label, tray, h('div', { class: 'actions' }, add)), h('p', { class: 'muted small' }, '説明の下書きはこの端末に保存します。選択中のファイルは、ページを再読み込みすると選び直しになります。'));
}

async function training(target, kind, name, cleanup) {
  const rec = await (kind === 'character' ? API.character(name) : API.style(name));
  const steps = input(`${kind}:${name}:steps`, '1200', { type: 'number', min: 1, step: 1 });
  target.append(h('div', { class: 'training-summary' }, h('div', { class: 'mini-stack' }, rec.samples.slice(0, 3).map(s => picture(s.path, '学習用の参考画像', { plain: true }))), h('div', {}, h('h3', {}, `${rec.samples.length} 枚から、${name}を覚えます`), h('p', { class: 'muted' }, rec.lora_name ? '学習済みです。参考画像や説明を変えたら、ここで学習し直せます。' : '学習には時間がかかります。開始すると実際の学習ステップを表示します。'))),
    advanced(field('学習ステップ', steps, 'まずは 1200。画像を追加しただけでは学習は始まりません。')),
    taskPanel({ kind: 'lora_train', name, tool: kind === 'character' ? 'train_character_lora' : 'train_style_lora' }, '学習', rec.lora_name ? 'この内容で学習し直す' : 'この内容で学習する', () => (kind === 'character' ? API.train : API.trainStyle)(name, number(steps)), cleanup));
}
async function styleSelect(ctx, key) {
  const styles = await API.styles();
  const select = h('select', { onchange: event => saveDraft(`${key}:style`, event.target.value) }, h('option', { value: '' }, 'キャラクターの設定を使う'), styles.filter(s => s.lora_name).map(s => h('option', { value: s.name }, s.name)));
  select.value = draft(`${key}:style`, ''); return select;
}
async function previewStep(target, ctx, styled, cleanup) {
  const name = ctx.character, style = styled ? ctx.style : ''; const key = `preview:${name}:${style}`;
  const tags = input(`${key}:tags`, 'full body, standing, front view, looking at viewer', { multiline: true, rows: 3 }); const seed = seedControl(key);
  target.append(field('どんな姿で確かめますか？', tags, '本人らしさ、衣装、顔を見比べましょう。内容を英語で指定できます。'), advanced(field('Seed', seed, '同じ数値で構図を比較できます。')),
    taskPanel({ kind: 'preview', name, style }, 'プレビュー', '2 枚で確かめる', () => API.previewCharacter(name, requireText(tags, '内容'), number(seed), 2, style), cleanup));
  if (styled) {
    const strength = input(`${key}:strength`, '0.7', { type: 'number', min: 0.1, max: 2, step: 0.1 });
    target.append(h('div', { class: 'callout stack' }, h('h3', {}, 'この組み合わせを、今後も使う'), h('p', { class: 'muted' }, 'プレビューは保存済みの強さ（未設定なら 0.7）で生成します。ここで変えた強さは、保存後の生成から反映されます。'), field('画風の強さ', strength), button('キャラクターの画風として保存', e => action(e.currentTarget, async () => { await API.setCharacterStyle(name, style, number(strength)); notice('今後使う画風を保存しました'); }), 'quiet')));
  }
}
async function drawing(target, ctx, kind, cleanup) {
  const name = kind === 'character' ? ctx.character : ctx.style; const key = `draw:${kind}:${name}`;
  const prompt = input(`${key}:prompt`, '', { multiline: true, rows: 5, placeholder: '例：standing by the window, morning light, holding a cup' });
  const seed = seedControl(key); const style = kind === 'character' ? await styleSelect(ctx, key) : null;
  target.append(field('次は、どんな一枚に？', prompt, '場所、ポーズ、衣装、構図など。絵柄は学習した画像から引き継ぎます。'), style ? field('合わせる画風', style) : null, advanced(field('Seed', seed)), taskPanel(kind === 'character' ? { kind: 'from_bible', name } : { kind: 'image', style: name }, '新しい一枚', 'この内容で描く', () => kind === 'character' ? API.fromBible(name, requireText(prompt, '描きたい内容'), number(seed), style.value) : API.image(requireText(prompt, '描きたい内容'), name, number(seed)), cleanup));
}
async function sheet(target, ctx, styled, cleanup) {
  const name = ctx.character; const rec = await API.character(name); const seed = seedControl(`sheet:${name}`);
  const existing = h('div', { class: 'stack' }); const edit = h('div', { class: 'stack' }); let editingReady = false; let refreshEditor;
  const showExisting = record => { if (record.bible?.sheet_path) existing.replaceChildren(h('h3', {}, '保存してある設定画'), picture(record.bible.sheet_path, `${name}の設定画`, { version: record.bible.at })); };
  showExisting(rec);
  const update = async () => { const fresh = await API.character(name); if (!target.isConnected) return; showExisting(fresh); if (fresh.bible && !editingReady) { editingReady = true; refreshEditor = await redraw(edit, name, fresh, cleanup, showExisting); } else refreshEditor?.(fresh); };
  target.append(h('p', { class: 'muted' }, '23 パネルを順に描き、設定画にまとめます。前の設定画は、新しい一枚が完成するまで残ります。'), advanced(field('Seed', seed)), taskPanel({ kind: 'character_bible', name }, '設定画', rec.bible ? '新しい設定画を作る' : '設定画を作る', () => API.bible(name, number(seed), styled ? ctx.style : ''), cleanup, () => update().catch(error => notice(error.message, true)), { hideCompletedImages: true }), existing, edit);
  if (rec.bible) { editingReady = true; refreshEditor = await redraw(edit, name, rec, cleanup, showExisting); }
}
async function redraw(target, name, rec, cleanup, updated) {
  const panels = await API.panels(); const key = `redraw:${name}`; let selected = panels.find(p => p.key === draft(`${key}:panel`)) || panels[0];
  const picker = h('div', { class: 'panel-picker' }); const selectedTitle = h('h3');
  const tags = h('textarea', { rows: 3, oninput: e => saveDraft(`${key}:${selected.key}:tags`, e.target.value) });
  const avoid = h('input', { placeholder: '例：frills, boots', oninput: e => saveDraft(`${key}:${selected.key}:avoid`, e.target.value) }); const seed = seedControl(key);
  const paint = () => {
    saveDraft(`${key}:panel`, selected.key); const override = rec.panel_overrides?.[selected.key] || {};
    selectedTitle.textContent = `${selected.section} · ${selected.label}`; tags.value = draft(`${key}:${selected.key}:tags`, override.tags || ''); tags.placeholder = selected.tags; avoid.value = draft(`${key}:${selected.key}:avoid`, override.avoid || '');
    picker.replaceChildren(...panels.map(panel => {
      const path = rec.bible?.panels_dir ? `${rec.bible.panels_dir}/${panel.key}.png` : '';
      const tile = button([path ? picture(path, panel.label, { plain: true, version: rec.bible?.at }) : icon('image'), h('span', {}, panel.label)], () => { selected = panel; paint(); }, `panel-tile ${selected.key === panel.key ? 'selected' : ''}`); tile.setAttribute('aria-pressed', String(selected.key === panel.key)); return tile;
    }));
  }; paint();
  target.append(h('details', { class: 'redraw-editor' }, h('summary', {}, icon('tool'), '気になるところを描き直す'), h('div', { class: 'stack' }, h('p', { class: 'muted' }, '画像から直すパネルを選んでください。指定した内容は、次の設定画にも引き継がれます。'), picker, selectedTitle, field('どう直しますか？', tags, '空欄なら、このパネルの既定の内容で描き直します。'), field('避けたいもの', avoid), advanced(field('Seed', seed)), taskPanel({ kind: 'redraw_panel', name }, 'パネルの描き直し', '選んだパネルを描き直す', () => API.redraw(name, selected.key, tags.value, number(seed), avoid.value), cleanup, job => {
    // The old picture remains visible in the result for side-by-side comparison.
    if (job.previous) { const previous = h('div', { class: 'comparison' }, h('h3', {}, '描き直す前'), picture(job.previous, '描き直す前')); const old = target.querySelector('.comparison'); old?.remove(); target.append(previous); }
    API.character(name).then(fresh => { if (!target.isConnected) return; rec = fresh; paint(); updated(fresh); }).catch(error => notice(error.message, true));
  }))));
  return fresh => { rec = fresh; paint(); };
}

export function flow(root, id) {
  const spec = FLOWS.find(item => item.id === id); if (!spec) { location.hash = '#/'; return () => {}; }
  const ctx = state.flow; let index = Math.min(ctx.step?.[id] || 0, spec.steps.length - 1); let version = 0; let cleanup = []; let disposed = false;
  const crumbs = h('ol', { class: 'steps', 'aria-label': '制作の工程' }); const body = h('section', { class: 'step-body stack' }); const aside = h('aside', { class: 'context-card' }); const nav = h('footer', { class: 'step-navigation' });
  const isStyle = ['style', 'styleonly'].includes(id);
  const keyKind = isStyle ? 'style' : 'character';
  const hints = { sheet: ['まず、作りたい子を選びましょう。', '画像と説明を一枚ずつ確かめましょう。', 'ここで初めて学習を始めます。', '顔や衣装を見て、先へ進むか決めましょう。', '全体を見て、気になるパネルを直せます。'], draw: ['描きたいキャラクターを選びましょう。', '思い浮かべた場面を、言葉にしてみましょう。'], restyle: ['画風を変えたいキャラクターを選びましょう。', '試してみたい画風を選びましょう。', '顔と衣装が保たれているか確かめましょう。', '選んだ画風で設定画も作れます。'], style: ['この画風に、名前をつけましょう。', '好きな線や色づかいが伝わる画像を。', '画像の描き方を覚えます。', '別の被写体でも、好きな絵になりますか？'], styleonly: ['使いたい画風を選びましょう。', '被写体は自由に。言葉から描いてみましょう。'] };
  let contextVersion = 0;
  const refreshContext = async supplied => {
    if (disposed) return;
    const current = ++contextVersion;
    const name = ctx[keyKind]; const rec = supplied || (name ? await (isStyle ? API.style(name) : API.character(name)).catch(() => null) : null);
    if (disposed || current !== contextVersion) return;
    aside.replaceChildren(h('p', { class: 'eyebrow' }, 'YOUR PROJECT'), rec ? picture(cover(rec), rec.name) : h('div', { class: 'context-placeholder' }, icon(spec.icon, 48)), h('h3', {}, rec?.name || 'これから始まる一枚'), h('p', { class: 'muted small' }, rec ? `${rec.samples.length} 枚の参考画像 · ${rec.lora_name ? '学習済み' : '未学習'}` : '画像を見ながら、一歩ずつ。'), h('hr'), h('p', { class: 'small' }, hints[id][index]), h('p', { class: 'muted small' }, '前の工程へ戻って直せます。学習と生成は、ボタンを押したときに始まります。'));
  };
  const valid = async destination => {
    if (destination === 0) return true;
    if (!ctx[keyKind]) throw new Error(isStyle ? '画風を選んでください。' : 'キャラクターを選んでください。');
    const rec = await (isStyle ? API.style(ctx.style) : API.character(ctx.character));
    if (['sheet', 'style'].includes(id)) {
      if (destination >= 2 && !rec.samples.length) throw new Error('まず参考画像を追加してください。');
      if (destination >= 3 && !rec.lora_name) throw new Error('学習を完了してから、プレビューへ進んでください。');
    } else if (!rec.lora_name) throw new Error('このキャラクター・画風は未学習です。画像を集めるコースから学習してください。');
    if (id === 'restyle' && destination >= 2) { if (!ctx.style || !(await API.style(ctx.style)).lora_name) throw new Error('学習済みの画風を選んでください。'); }
    return true;
  };
  const move = async destination => { try { await valid(destination); if (disposed) return; index = destination; await render(); body.focus({ preventScroll: true }); body.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (error) { notice(error.message, true); } };
  async function render() {
    const current = ++version; cleanup.forEach(fn => fn()); const ownedCleanup = []; cleanup = ownedCleanup;
    ctx.step = { ...ctx.step, [id]: index }; state.saveFlow();
    crumbs.replaceChildren(...spec.steps.map((title, step) => h('li', {}, h('button', { type: 'button', class: `step ${step === index ? 'active' : step < index ? 'past' : ''}`, 'aria-current': step === index ? 'step' : null, onclick: () => move(step) }, h('span', { class: 'step-number' }, step < index ? icon('check', 14) : step + 1), h('span', {}, title)))));
    body.replaceChildren(h('div', { class: 'step-heading' }, h('p', { class: 'eyebrow' }, `STEP ${String(index + 1).padStart(2, '0')} / ${String(spec.steps.length).padStart(2, '0')}`), h('h2', {}, spec.steps[index]), h('p', { class: 'muted' }, hints[id][index])));
    const content = h('div', { class: 'stack' }); body.append(content);
    nav.replaceChildren(index > 0 ? button('← 前の工程', () => move(index - 1), 'quiet') : link('スタジオへ', '#/', 'text-link'), h('span', { class: 'muted small' }, `${index + 1} / ${spec.steps.length}`), index < spec.steps.length - 1 ? button([`次へ：${spec.steps[index + 1]}`, icon('arrow', 18)], () => move(index + 1)) : link(['作品を見る', icon('arrow')], '#/library'));
    try {
      await refreshContext(); if (disposed || current !== version) return;
      if (index === 0) await choose(content, keyKind, ctx, ['sheet', 'style'].includes(id), () => refreshContext().catch(error => notice(error.message, true)));
      else if (id === 'restyle' && index === 1) await choose(content, 'style', ctx, false, () => {});
      else if (['sheet', 'style'].includes(id) && index === 1) await samples(content, keyKind, ctx[keyKind], ownedCleanup, rec => refreshContext(rec).catch(error => notice(error.message, true)));
      else if (['sheet', 'style'].includes(id) && index === 2) await training(content, keyKind, ctx[keyKind], ownedCleanup);
      else if (id === 'sheet' && index === 3 || id === 'restyle' && index === 2) await previewStep(content, ctx, id === 'restyle', ownedCleanup);
      else if (id === 'sheet' && index === 4 || id === 'restyle' && index === 3) await sheet(content, ctx, id === 'restyle', ownedCleanup);
      else await drawing(content, ctx, keyKind, ownedCleanup);
    } catch (error) { if (current === version && !disposed) errorState(content, error); }
    finally { if (disposed || current !== version) ownedCleanup.forEach(fn => fn()); }
  }
  body.tabIndex = -1;
  root.replaceChildren(pageHead('CREATIVE WORKFLOW', spec.title, spec.desc, link('すべてのコース', '#/', 'text-link')), crumbs, h('div', { class: 'flow-layout' }, h('div', { class: 'flow-main' }, body, nav), aside));
  valid(index).catch(() => { index = 0; }).then(() => { if (!disposed) render(); });
  return () => { disposed = true; version++; cleanup.forEach(fn => fn()); };
}

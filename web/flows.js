import { API } from './api.js?v=studio-7';
import { layoutEditor } from './layout.js?v=studio-3';
import { state } from './state.js?v=studio-3';
import { h, icon, field, button, link, picture, empty, notice, action, pageHead, errorState, confirmAction } from './ui.js?v=studio-3';
import { taskPanel, runJob } from './jobs.js?v=studio-7';
import { draft, saveDraft, clearDraft, pendingFiles } from './drafts.js?v=studio-3';
import { commentEditor, referenceNotes, flushCaptions, saveCaption } from './intent.js?v=studio-3';
import { learning } from './learning.js?v=studio-3';
import { characterStrength } from './strength.js?v=studio-3';
import { previewGallery } from './preview.js?v=studio-9';

export const FLOWS = [
  { id: 'sheet', title: 'キャラクターを育てる', desc: '参考画像から、その子らしい設定画へ。', icon: 'layers', steps: ['キャラクター', '参考画像', '学習', 'プレビュー', '一枚シート', '設定画'] },
  { id: 'draw', title: '新しい一枚を描く', desc: 'あのキャラクターを、まだ見ぬ場面に。', icon: 'spark', steps: ['キャラクター', '描く'] },
  { id: 'restyle', title: '画風を着せかえる', desc: '同じキャラクターに、違う絵の表情を。', icon: 'palette', steps: ['キャラクター', '画風', 'プレビュー', '一枚シート', '設定画'] },
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
export function previewIntentJob(editor, content) { return content === 'full body, standing, front view, looking at viewer' ? editor.confirmedJob() : ''; }

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
  const name = h('input', { required: true, placeholder: isChar ? 'キャラクターの名前' : '例：淡い水彩', autocomplete: 'off', maxlength: 100 });
  const desc = h('textarea', { rows: 2, placeholder: isChar ? '例：銀髪の成人女性。旅人で、青いコートを着ている。' : 'どんな線や色づかいが好きですか？' });
  const trigger = h('input', { placeholder: '空欄なら自動で決めます' });
  const attr = h('input', { placeholder: '設定画に添える短いメモ' });
  const create = button([icon('plus'), `${noun}を登録`], e => action(e.currentTarget, async () => {
    const value = requireText(name, '名前');
    if (items.some(item => item.name === value)) throw new Error('同じ名前があるので、上のカードから選んでください。');
    const rec = await (isChar ? API.createCharacter(value, requireText(desc, 'キャラクターの説明'), attr.value, trigger.value) : API.createStyle(value, desc.value));
    items.push(rec); ctx[kind] = rec.name; state.saveFlow(); paint(); changed(); details.open = false; notice(`${rec.name}を登録しました。参考画像へ進めます。`);
  }));
  const details = h('details', { class: 'create-card', open: !items.length }, h('summary', {}, icon('plus'), `新しい${noun}を作る`), h('div', { class: 'stack' }, field('名前', name), field(isChar ? 'どんなキャラクター？' : '画風のメモ', desc, isChar ? '短い説明で大丈夫です。画像ごとの希望は次に書けます。' : ''), isChar ? advanced(field('呼び出し語', trigger), field('属性メモ', attr)) : null, create));
  target.append(details);
}

export async function samples(target, kind, name, cleanup, changed, availability = () => {}) {
  const isChar = kind === 'character'; const key = `${kind}:${name}`;
  const load = () => isChar ? API.character(name) : API.style(name);
  const removeSample = isChar ? API.removeSample : API.removeStyleSample;
  const addSample = isChar ? API.addSamples : API.addStyleSamples;
  const list = h('div', { class: 'sample-grid' }); const count = h('span', { class: 'badge' });
  const heading = h('div', { class: 'section-heading' }, h('h3', {}, '参考画像'), count);
  target.append(heading, h('p', { class: 'muted' }, '画像を選ぶと自動で追加されます。4枚以上を目安に、特徴が分かる画像を選んでください。'), list);
  const paint = rec => {
    record = rec;
    count.textContent = `${rec.samples.length} 枚`;
    list.replaceChildren(...rec.samples.map((sample, index) => {
      const capKey = `${key}:caption:${sample.index}:${sample.path}`;
      const cap = h('textarea', { rows: 2, placeholder: '例：この画像の顔立ちを使いたい（任意）', 'aria-label': `画像 ${index + 1} の説明` }, draft(capKey, sample.caption || ''));
      const saved = h('span', { class: 'draft-status' }, cap.value !== (sample.caption || '') ? '未保存' : '保存済み');
      cap.addEventListener('input', () => { saveDraft(capKey, cap.value); saved.textContent = cap.value !== (sample.caption || '') ? '未保存' : '保存済み'; });
      cap.addEventListener('blur', async () => {
        const value = cap.value;
        if (value === (sample.caption || '')) return;
        saved.textContent = '保存中…';
        try {
          await saveCaption(kind, name, sample, value); sample.caption = value;
          if (cap.value === value) { clearDraft(capKey); saved.textContent = '保存済み'; }
        } catch (error) { saved.textContent = '保存できませんでした'; notice(error.message, true); }
      });
      const remove = button('外す', e => action(e.currentTarget, async () => {
        if (!await confirmAction(`画像 ${index + 1} を参考画像から外しますか？`)) return;
        const rec = await removeSample(name, sample.index); clearDraft(capKey); paint(rec); renderPending(); changed(rec); notice('参考画像から外しました。元のアップロード画像は残っています。');
      }), 'text-button danger');
      return h('article', { class: 'sample-card' }, picture(sample.path, `参考画像 ${index + 1}`), h('div', { class: 'sample-content stack' }, h('div', { class: 'section-heading' }, h('strong', {}, `画像 ${index + 1}`), saved), field('この画像への希望', cap), remove));
    }));
    if (!rec.samples.length) list.append(empty('まだ画像がありません', '上の「画像を選ぶ」から追加してください。'));
  };
  let record = await load(); paint(record);
  if (!pendingFiles.has(key)) pendingFiles.set(key, []);
  const pending = pendingFiles.get(key);
  pending.listeners ||= new Set();
  const notifyPending = () => pending.listeners.forEach(fn => fn());
  const tray = h('div', { class: 'sample-grid pending-grid' });
  const label = h('p', { class: 'upload-status', role: 'status' });
  const fileInput = h('input', { type: 'file', multiple: true, accept: 'image/*', class: 'sr-only', id: `sample-upload-${kind}`, onchange: () => { addFiles(fileInput.files); fileInput.value = ''; } });
  const drop = h('label', { class: 'dropzone', for: fileInput.id }, fileInput, h('span', { class: 'upload-symbol' }, icon('upload', 24)), h('strong', {}, '画像を選ぶ'), h('span', { class: 'muted small' }, '選択すると追加します・複数選択できます'));
  const addFiles = files => {
    if (pending.busy) return;
    for (const file of files) pending.push({ file, url: URL.createObjectURL(file), caption: '', status: '追加待ち' });
    if (pending.length) upload();
  };
  drop.addEventListener('dragover', event => { event.preventDefault(); drop.classList.add('dragging'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
  drop.addEventListener('drop', event => { event.preventDefault(); drop.classList.remove('dragging'); addFiles(event.dataTransfer.files); });
  const upload = () => {
    if (!pending.length || pending.busy) return;
    pending.busy = true; pending.error = ''; notifyPending();
    pending.promise = (async () => {
    try {
      while (pending.length) {
        const item = pending[0];
        if (!item.path) { item.status = '転送中'; notifyPending(); item.path = (await API.upload([item.file]))[0].path; }
        item.status = '保存中'; notifyPending();
        const rec = await addSample(name, item.path, item.caption);
        pending.shift(); URL.revokeObjectURL(item.url); pending.latest = rec; notifyPending();
      }
    } catch (error) {
      if (pending[0]) pending[0].status = '追加できませんでした';
      pending.error = error.message;
      notice(`画像を追加できませんでした：${error.message}`, true);
    } finally { pending.busy = false; notifyPending(); }
    })();
  };
  const retry = button('追加できなかった画像を再送する', upload, 'quiet');
  function renderPending() {
    label.textContent = pending.busy ? `画像を追加しています… 残り ${pending.length} 枚` : pending.error ? `追加できませんでした：${pending.error}` : `${record.samples.length} 枚を追加済み`;
    tray.replaceChildren(...pending.map((item, index) => {
      return h('article', { class: 'sample-card pending' }, h('div', { class: 'picture' }, h('img', { src: item.url, alt: item.file.name })), h('div', { class: 'sample-content stack' }, h('strong', { class: 'truncate' }, item.file.name), h('small', { class: 'muted' }, item.status), pending.busy ? null : button('この画像を取り消す', () => { pending.splice(index, 1); URL.revokeObjectURL(item.url); if (!pending.length) pending.error = ''; notifyPending(); }, 'text-button')));
    }));
    retry.hidden = !pending.error; retry.disabled = !!pending.busy; fileInput.disabled = !!pending.busy; drop.classList.toggle('uploading', !!pending.busy);
    availability(!pending.length && !pending.busy && !!record.samples.length, pending.busy ? '画像を追加しています。完了すると次へ進めます。' : pending.length ? '追加できなかった画像を再送するか、取り消してください。' : record.samples.length ? '' : '画像を選んでください。');
  }
  let lastRecord = pending.latest;
  const onPending = () => { if (pending.latest && pending.latest !== lastRecord) { lastRecord = pending.latest; record = pending.latest; paint(record); changed(record); } renderPending(); };
  pending.listeners.add(onPending); cleanup.push(() => pending.listeners.delete(onPending));
  const uploading = h('div', { class: 'upload-section stack' }, drop, label, tray, retry);
  target.insertBefore(uploading, list);
  renderPending();
  const notes = await referenceNotes(target, { name, kind });
  if (pending.length && !pending.busy && !pending.error) upload();
  return async () => { await pending.promise; if (pending.length) throw new Error('追加できなかった画像を確認してください。'); await flushCaptions(kind, name); await notes.save(); };
}
async function styleSelect(ctx, key) {
  const styles = await API.styles();
  const select = h('select', { onchange: event => saveDraft(`${key}:style`, event.target.value) }, h('option', { value: '' }, 'キャラクターの設定を使う'), styles.filter(s => s.lora_name).map(s => h('option', { value: s.name }, s.name)));
  select.value = draft(`${key}:style`, ''); return select;
}
async function previewStep(target, ctx, styled, cleanup, setReady, next) {
  const name = ctx.character, style = styled ? ctx.style : ''; const key = `preview:${name}:${style}`;
  const wishes = h('section', { class: 'stack' }, h('h3', {}, '全体への注文'), h('p', { class: 'muted small' }, 'ここでは元の参考画像を参照して、生成する内容を指定します。生成画像への指摘は、その画像のOK・NGと理由欄へ書いてください。'));
  const editor = await commentEditor(wishes, { name, kind: 'character', stage: 'preview', cleanup });
  target.append(h('p', {}, '10枚の生成画像を見て、OK・NGを指定します。両方の判定でLoRAを修正し、結果を確かめてから一枚シートへ進めます。'), wishes);
  let gallery;
  const tags = input(`${key}:tags`, 'full body, standing, front view, looking at viewer', { multiline: true, rows: 3 }); const seed = seedControl(key);
  target.append(advanced(characterStrength(await API.character(name)), field('英語の自由入力（解釈した注文を使わない場合）', tags, '注文を解釈して使う場合は既定値のままにします。姿勢などは上の制作への注文へ書いてください。'), field('Seed', seed, '同じ数値で構図を比較できます。')),
    taskPanel({ kind: 'preview', name, style }, 'プレビュー', '10枚のプレビューを生成する', async () => { await editor.save(); await gallery?.flush(); gallery?.followNext(); const content = requireText(tags, '内容'); return API.previewCharacter(name, content, number(seed), 10, style, previewIntentJob(editor, content)); }, cleanup, job => gallery?.select(job.job_id), { hideImages: true }));
  gallery = await previewGallery(target, name, style, cleanup, setReady, next);
  if (styled) {
    const strength = input(`${key}:strength`, '0.7', { type: 'number', min: 0.1, max: 2, step: 0.1 });
    target.append(h('div', { class: 'callout stack' }, h('h3', {}, 'この組み合わせを、今後も使う'), h('p', { class: 'muted' }, 'プレビューは保存済みの強さ（未設定なら 0.7）で生成します。ここで変えた強さは、保存後の生成から反映されます。'), field('画風の強さ', strength), button('キャラクターの画風として保存', e => action(e.currentTarget, async () => { await API.setCharacterStyle(name, style, number(strength)); notice('今後使う画風を保存しました'); }), 'quiet')));
  }
  return async () => { await editor.save(); await gallery.flush(); };
}
async function judgeSheet(target, ctx, styled, cleanup, setReady, next) {
  const name = ctx.character, style = styled ? ctx.style : '';
  let rec = await API.character(name);
  const seed = seedControl(`sheet-judge:${name}`);
  const spec = { kind: 'character_sheet', name, style };
  const frame = h('div', { class: 'stack' });
  let jobId = rec.pending_sheet_job_id || rec.approved_sheet_job_id || '';
  let approve, redraw;
  const refresh = (record, job) => {
    rec = record;
    if (job?.job_id) jobId = job.job_id;
    const path = job?.path || rec.pending_sheet || rec.approved_sheet;
    const done = job?.status === 'completed' && job.path || !!rec.pending_sheet && (!job || job.status === 'completed');
    const approved = !!(rec.approved_sheet && rec.approved_sheet_job_id && rec.approved_sheet_job_id === jobId);
    frame.replaceChildren(path
      ? picture(path, `${name}の一枚シート`, { version: jobId || rec.approved_sheet })
      : h('p', { class: 'muted' }, 'まだ一枚がありません。'));
    if (approve) approve.disabled = !done || approved;
    if (redraw) redraw.disabled = !done;
    setReady(approved, approved ? '' : done ? 'この一枚の合否を決めてください。' : '一枚を生成してください。');
  };
  approve = button('合格して設定画へ', e => action(e.currentTarget, async () => {
    if (!jobId) throw new Error('合格にする一枚がありません。');
    const record = await API.approveSheet(name, jobId);
    refresh(record, { job_id: jobId, status: 'completed', path: record.approved_sheet });
    await next();
  }));
  redraw = button('描き直す', e => action(e.currentTarget, async () => {
    const job = await runJob(spec, '一枚シート', () => API.regenerateSheet(name, 0, style));
    if (job) API.character(name).then(record => refresh(record, job)).catch(error => notice(error.message, true));
  }), 'quiet');
  target.append(
    h('p', {}, '向きを並べた参照シートを描きます。この一枚を見て合否を決めます。不合格なら同じ参照シートを描き直します。合格した絵が、次の設定画の起点になります。'),
    advanced(characterStrength(rec), field('Seed', seed, '同じ数値で構図を比較できます。')),
    taskPanel(spec, '一枚シート', '一枚を生成する', () => API.generateSheet(name, number(seed), style), cleanup, job => {
      API.character(name).then(record => refresh(record, job)).catch(error => notice(error.message, true));
    }),
    frame,
    h('div', { class: 'actions' }, approve, redraw),
  );
  refresh(rec);
  if (!rec.pending_sheet && !rec.approved_sheet) runJob(spec, '一枚シート', () => API.generateSheet(name, number(seed), style));
}
export function drawingInput(editor, mode, text) {
  if (mode === 'intent') return { prompt: '', intentJobId: editor.confirmedJob() };
  if (!text.trim()) throw new Error('英語の自由入力に描きたい内容を入力してください。');
  return { prompt: text, intentJobId: '' };
}
async function drawing(target, ctx, kind, cleanup) {
  const name = kind === 'character' ? ctx.character : ctx.style; const key = `draw:${kind}:${name}`;
  const editor = await commentEditor(target, { name, kind, stage: 'drawing', cleanup });
  const prompt = input(`${key}:prompt`, '', { multiline: true, rows: 5, placeholder: '例：standing by the window, morning light, holding a cup' });
  const seed = seedControl(key); const style = kind === 'character' ? await styleSelect(ctx, key) : null;
  const mode = h('select', { 'aria-label': '注文の使い方' }, h('option', { value: 'intent' }, '解釈して採用した注文で描く'), h('option', { value: 'english' }, '英語の自由入力で描く'));
  target.append(...(style ? [field('合わせる画風', style)] : []),
    advanced(field('注文の使い方', mode), kind === 'character' ? characterStrength(await API.character(name)) : null, field('英語の自由入力', prompt, '自由入力を選んだ時だけ使います。'), field('Seed', seed)),
    taskPanel(kind === 'character' ? { kind: 'from_bible', name } : { kind: 'image', style: name }, '新しい一枚', 'この内容で描く', async () => { await editor.save(); const selected = drawingInput(editor, mode.value, prompt.value); return kind === 'character' ? API.fromBible(name, selected.prompt, number(seed), style.value, selected.intentJobId) : API.image(selected.prompt, name, number(seed), selected.intentJobId); }, cleanup));
  return editor.save;
}
async function sheet(target, ctx, styled, cleanup) {
  const name = ctx.character; const rec = await API.character(name); const seed = seedControl(`sheet:${name}`);
  const layout = await layoutEditor(target, name, cleanup);
  const wishes = h('details', { class: 'optional-wishes' }, h('summary', {}, '設定画全体の見た目を調整する（任意）'));
  const editor = await commentEditor(wishes, { name, kind: 'character', stage: 'sheet', cleanup });
  wishes.open = !!wishes.querySelector('textarea').value; target.append(wishes);
  const existing = h('div', { class: 'stack' }); const edit = h('div', { class: 'stack' }); let editingReady = false; let refreshEditor;
  const showExisting = record => { if (record.bible?.sheet_path) existing.replaceChildren(h('h3', {}, '保存してある設定画'), picture(record.bible.sheet_path, `${name}の設定画`, { version: record.bible.at })); };
  showExisting(rec);
  const update = async () => { const fresh = await API.character(name); if (!target.isConnected) return; showExisting(fresh); if (fresh.bible && !editingReady) { editingReady = true; refreshEditor = await redraw(edit, name, fresh, cleanup, showExisting); } else await refreshEditor?.(fresh); };
  target.append(h('p', { class: 'muted' }, '保存した構成の項目を順に描き、設定画にまとめます。前の設定画は、新しい一枚が完成するまで残ります。'), advanced(characterStrength(rec), field('Seed', seed)), taskPanel({ kind: 'character_bible', name }, '設定画', rec.bible ? '新しい設定画を作る' : '設定画を作る', () => { layout.requireConfirmed(); return editor.save().then(() => API.bible(name, number(seed), styled ? ctx.style : '', editor.confirmedJob())); }, cleanup, () => update().catch(error => notice(error.message, true)), { hideCompletedImages: true }), existing, edit);
  if (rec.bible) { editingReady = true; refreshEditor = await redraw(edit, name, rec, cleanup, showExisting); }
  return async () => { await layout.save(); await editor.save(); await refreshEditor?.save(); };
}
async function redraw(target, name, rec, cleanup, updated) {
  let panels = await API.panels(name, true); const key = `redraw:${name}`; let selected = panels.find(p => p.key === draft(`${key}:panel`)) || panels[0];
  const picker = h('div', { class: 'panel-picker' }); const selectedTitle = h('h3');
  const commentBox = h('div'); let panelEditor, changing = false;
  const loadComment = async () => { panelEditor?.dispose(); commentBox.replaceChildren(); panelEditor = await commentEditor(commentBox, { name, kind: 'character', stage: 'panel', panel: selected.key, cleanup }); };
  const mode = h('select', { 'aria-label': 'パネルの注文の使い方' }, h('option', { value: 'intent' }, '解釈して採用した注文で描き直す'), h('option', { value: 'english' }, '英語の自由入力で描き直す'));
  const tags = h('textarea', { rows: 3, oninput: e => saveDraft(`${key}:${selected.key}:tags`, e.target.value) });
  const avoid = h('input', { placeholder: '例：frills, boots', oninput: e => saveDraft(`${key}:${selected.key}:avoid`, e.target.value) }); const seed = seedControl(key);
  const paint = () => {
    saveDraft(`${key}:panel`, selected.key); const override = rec.panel_overrides?.[selected.key] || {};
    selectedTitle.textContent = `${selected.section} · ${selected.label}`; tags.value = draft(`${key}:${selected.key}:tags`, override.tags || ''); tags.placeholder = selected.tags; avoid.value = draft(`${key}:${selected.key}:avoid`, override.avoid || '');
    picker.replaceChildren(...panels.map(panel => {
      const path = rec.bible?.panels_dir ? `${rec.bible.panels_dir}/${panel.key}.png` : '';
      const tile = button([path ? picture(path, panel.label, { plain: true, version: rec.bible?.at }) : icon('image'), h('span', {}, panel.label)], e => action(e.currentTarget, async () => { if (changing) return; changing = true; try { await panelEditor.save(); selected = panel; paint(); await loadComment(); } finally { changing = false; paint(); } }), `panel-tile ${selected.key === panel.key ? 'selected' : ''}`); tile.disabled = changing; tile.setAttribute('aria-pressed', String(selected.key === panel.key)); return tile;
    }));
  }; paint();
  await loadComment();
  // 出し直し候補: 同じ内容で seed だけ変えた 4 枚を並べ、選んだ一枚だけ設定画へ入れる。
  const candidates = h('div', { class: 'stack retry-candidates' });
  const showCandidates = job => {
    const panel = panels.find(p => p.key === job.panel); const label = panel ? `${panel.section} · ${panel.label}` : job.panel;
    const current = rec.bible?.panels_dir ? `${rec.bible.panels_dir}/${job.panel}.png` : '';
    const adopt = candidate => e => action(e.currentTarget, async () => {
      const done = await API.adoptPanel(name, job.job_id, candidate.seed);
      notice(`${label}を候補で差し替えました。前の絵は履歴に残っています。`);
      const fresh = await API.character(name); if (!target.isConnected) return; await refresh(fresh); updated(fresh); showCandidates(done);
    });
    candidates.replaceChildren(h('h3', {}, `${label} の出し直し候補`),
      h('p', { class: 'muted' }, job.adopted ? '採用した一枚を設定画へ入れました。別の候補に変えることもできます。' : '気に入った一枚を選ぶと、設定画のこの項目だけ差し替わります。選ぶまで設定画は変わりません。'),
      h('div', { class: 'result-grid' }, h('figure', {}, picture(current, `${label}（今の絵）`, { version: rec.bible?.at }), h('figcaption', {}, '今の絵')),
        ...job.candidates.map((candidate, index) => { const adopted = job.adopted?.seed === candidate.seed; return h('figure', { class: adopted ? 'adopted' : '' }, picture(candidate.path, `${label} 候補 ${index + 1}`), h('figcaption', {}, `候補 ${index + 1}`, adopted ? h('span', { class: 'badge green' }, '採用中') : button('この一枚を採用', adopt(candidate), 'small-button'))); })));
  };
  target.append(h('div', { class: 'stack' }, h('h3', {}, '気になる項目を出し直す'), h('p', { class: 'muted' }, '項目を選んで押すと、同じ内容のまま seed だけ変えた 4 枚を描きます。気に入った一枚を選ぶまで設定画は変わりません。'), picker, selectedTitle,
    taskPanel({ kind: 'panel_retry', name }, '項目の出し直し', 'この項目を 4 枚描き直す', async () => { await panelEditor.save(); return API.retryPanel(name, selected.key, 4); }, cleanup, showCandidates, { hideCompletedImages: true }), candidates));
target.append(h('details', { class: 'redraw-editor' }, h('summary', {}, icon('tool'), '注文を付けて描き直す'), h('div', { class: 'stack' }, h('p', { class: 'muted' }, '上で選んだ項目に、言葉で注文を付けて描き直します。「このパネルに残す」は生成が成功してから保存し、「今回だけ」は次回へ残しません。'), commentBox, field('注文の使い方', mode, '採用した注文を使う時は、詳細設定の英語欄は使いません。'), advanced(field('英語の自由入力', tags, '自由入力はパネルの内容全体を置き換えます。採用した条件とは併用できません。'), field('避けたいもの（英語）', avoid), field('Seed', seed)), taskPanel({ kind: 'redraw_panel', name }, 'パネルの描き直し', '選んだパネルを描き直す', async () => { await panelEditor.save(); const interpreted = mode.value === 'intent'; return API.redraw(name, selected.key, interpreted ? '' : tags.value, number(seed), interpreted ? '' : avoid.value, interpreted ? panelEditor.confirmedJob() : '', mode.value); }, cleanup, job => {
    // The old picture remains visible in the result for side-by-side comparison.
    if (job.previous) { const previous = h('div', { class: 'comparison' }, h('h3', {}, '描き直す前'), picture(job.previous, '描き直す前')); const old = target.querySelector('.comparison'); old?.remove(); target.append(previous); }
    API.character(name).then(async fresh => { if (!target.isConnected) return; await refresh(fresh); updated(fresh); }).catch(error => notice(error.message, true));
  }))));
  const refresh = async fresh => {
    const changedSheet = rec.bible?.job_id !== fresh.bible?.job_id;
    rec = fresh;
    if (fresh.bible?.layout) panels = fresh.bible.layout.map(p => ({ ...p, tags: p.parts.map(part => part.description_en).filter(Boolean).join(', ') }));
    selected = panels.find(p => p.key === selected.key) || panels[0];
    paint();
    if (changedSheet) await loadComment();
  };
  refresh.save = () => panelEditor.save();
  return refresh;
}

export function flow(root, id) {
  const spec = FLOWS.find(item => item.id === id); if (!spec) { location.hash = '#/'; return () => {}; }
  const ctx = state.flow; let index = Math.min(ctx.step?.[id] || 0, spec.steps.length - 1); let version = 0; let cleanup = []; let disposed = false; let saveStep = async () => {};
  const crumbs = h('ol', { class: 'steps', 'aria-label': '制作の工程' }); const body = h('section', { class: 'step-body stack' }); const aside = h('aside', { class: 'context-card' }); const nav = h('footer', { class: 'step-navigation' });
  const isStyle = ['style', 'styleonly'].includes(id);
  const keyKind = isStyle ? 'style' : 'character';
  let nextButton, nextHint, canAdvance = false, furthest = 0;
  const availability = (ready, reason = '') => {
    canAdvance = ready;
    if (nextButton) nextButton.disabled = !ready;
    if (nextHint) nextHint.textContent = reason;
    crumbs.querySelectorAll('button').forEach((control, step) => { control.disabled = step > index && (!ready || step > furthest); });
  };
  const hints = { sheet: ['まず、作りたい子を選びましょう。', '画像と説明を一枚ずつ確かめましょう。', 'ここで初めて学習を始めます。', '顔や衣装を見て、先へ進むか決めましょう。', '一枚を見て、設定画の起点にするか決めましょう。', '全体を見て、気になるパネルを直せます。'], draw: ['描きたいキャラクターを選びましょう。', '思い浮かべた場面を、言葉にしてみましょう。'], restyle: ['画風を変えたいキャラクターを選びましょう。', '試してみたい画風を選びましょう。', '顔と衣装が保たれているか確かめましょう。', '一枚を見て、設定画の起点にするか決めましょう。', '選んだ画風で設定画も作れます。'], style: ['この画風に、名前をつけましょう。', '好きな線や色づかいが伝わる画像を。', '画像の描き方を覚えます。', '別の被写体でも、好きな絵になりますか？'], styleonly: ['使いたい画風を選びましょう。', '被写体は自由に。言葉から描いてみましょう。'] };
  let contextVersion = 0;
  const refreshContext = async supplied => {
    if (disposed) return;
    const current = ++contextVersion;
    const name = ctx[keyKind]; const rec = supplied || (name ? await (isStyle ? API.style(name) : API.character(name)).catch(() => null) : null);
    if (disposed || current !== contextVersion) return;
    const bibleReady = !!(rec.approved_sheet || rec.bible);
    furthest = !rec ? 0 : id === 'sheet' ? (rec.lora_name ? (bibleReady ? 5 : 4) : rec.samples.length ? 2 : 1)
      : id === 'style' ? (rec.lora_name ? spec.steps.length - 1 : rec.samples.length ? 2 : 1)
      : id === 'restyle' ? (bibleReady ? 4 : 3)
      : spec.steps.length - 1;
    aside.replaceChildren(h('p', { class: 'eyebrow' }, 'YOUR PROJECT'), rec ? picture(cover(rec), rec.name) : h('div', { class: 'context-placeholder' }, icon(spec.icon, 48)), h('h3', {}, rec?.name || 'これから始まる一枚'), h('p', { class: 'muted small' }, rec ? `${rec.samples.length} 枚の参考画像 · ${rec.lora_name ? '学習済み' : '未学習'}` : '画像を見ながら、一歩ずつ。'), h('hr'), h('p', { class: 'small' }, hints[id][index]), h('p', { class: 'muted small' }, '前の工程へ戻って直せます。学習と生成は、ボタンを押したときに始まります。'));
    if (index === 0) availability(!!rec && (['sheet', 'style'].includes(id) || !!rec.lora_name), rec ? !['sheet', 'style'].includes(id) && !rec.lora_name ? '学習済みのキャラクター・画風を選んでください。' : '' : '選ぶか、新しく登録してください。');
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
    if ((id === 'sheet' && destination >= 5 || id === 'restyle' && destination >= 4) && !rec.approved_sheet && !rec.bible) {
      throw new Error('合格した一枚を、設定画の起点にしてください。');
    }
    return true;
  };
  const move = async destination => { if (destination > index && !canAdvance) return; try { await saveStep(); await valid(destination); if (disposed) return; index = destination; await render(); body.focus({ preventScroll: true }); body.scrollIntoView({ behavior: 'smooth', block: 'start' }); } catch (error) { notice(error.message, true); } };
  async function render() {
    const current = ++version; cleanup.forEach(fn => fn()); const ownedCleanup = []; cleanup = ownedCleanup;
    saveStep = async () => {};
    ctx.step = { ...ctx.step, [id]: index }; state.saveFlow();
    crumbs.replaceChildren(...spec.steps.map((title, step) => h('li', {}, h('button', { type: 'button', class: `step ${step === index ? 'active' : step < index ? 'past' : ''}`, 'aria-current': step === index ? 'step' : null, onclick: () => move(step) }, h('span', { class: 'step-number' }, step < index ? icon('check', 14) : step + 1), h('span', {}, title)))));
    body.replaceChildren(h('div', { class: 'step-heading' }, h('p', { class: 'eyebrow' }, `STEP ${String(index + 1).padStart(2, '0')} / ${String(spec.steps.length).padStart(2, '0')}`), h('h2', {}, spec.steps[index]), h('p', { class: 'muted' }, hints[id][index])));
    const content = h('div', { class: 'stack' }); body.append(content);
    nextButton = index < spec.steps.length - 1 ? button([`次へ：${spec.steps[index + 1]}`, icon('arrow', 18)], () => move(index + 1)) : null;
    nextHint = h('p', { class: 'small muted', role: 'status' });
    nav.replaceChildren(index > 0 ? button('← 前の工程', () => move(index - 1), 'quiet') : link('スタジオへ', '#/', 'text-link'), h('div', { class: 'next-step' }, nextHint, nextButton || link(['作品を見る', icon('arrow')], '#/library')));
    availability(false, '読み込んでいます…');
    try {
      await refreshContext(); if (disposed || current !== version) return;
      const setReady = (ready, reason) => { if (!disposed && current === version) { if (ready && index === 2 && ['sheet', 'style'].includes(id)) furthest = spec.steps.length - 1; availability(ready, reason); } };
      if (index > 0 && !(['sheet', 'style'].includes(id) && [1, 2].includes(index)) && !(id === 'sheet' && index === 4) && !(id === 'restyle' && index === 3)) setReady(true);
      let nextSave = async () => {};
      if (index === 0) await choose(content, keyKind, ctx, ['sheet', 'style'].includes(id), () => refreshContext().catch(error => notice(error.message, true)));
      else if (id === 'restyle' && index === 1) await choose(content, 'style', ctx, false, () => {});
      else if (['sheet', 'style'].includes(id) && index === 1) nextSave = await samples(content, keyKind, ctx[keyKind], ownedCleanup, rec => refreshContext(rec).catch(error => notice(error.message, true)), setReady);
      else if (['sheet', 'style'].includes(id) && index === 2) nextSave = await learning(content, keyKind, ctx[keyKind], ownedCleanup, setReady);
      else if (id === 'sheet' && index === 3 || id === 'restyle' && index === 2) nextSave = await previewStep(content, ctx, id === 'restyle', ownedCleanup, setReady, () => move(index + 1));
      else if (id === 'sheet' && index === 4 || id === 'restyle' && index === 3) await judgeSheet(content, ctx, id === 'restyle', ownedCleanup, setReady, () => move(index + 1));
      else if (id === 'sheet' && index === 5 || id === 'restyle' && index === 4) nextSave = await sheet(content, ctx, id === 'restyle', ownedCleanup);
      else nextSave = await drawing(content, ctx, keyKind, ownedCleanup);
      if (!disposed && current === version) saveStep = nextSave;
    } catch (error) { if (current === version && !disposed) errorState(content, error); }
    finally { if (disposed || current !== version) ownedCleanup.forEach(fn => fn()); }
  }
  body.tabIndex = -1;
  const leave = async event => {
    const anchor = event.target.closest('a[href^="#/"]');
    if (!anchor || event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const destination = anchor.getAttribute('href');
    if (destination === location.hash) return;
    event.preventDefault();
    try { await saveStep(); if (!disposed) location.hash = destination; }
    catch (error) { notice(error.message, true); }
  };
  document.addEventListener('click', leave);
  root.replaceChildren(pageHead('CREATIVE WORKFLOW', spec.title, spec.desc, link('すべてのコース', '#/', 'text-link')), crumbs, h('div', { class: 'flow-layout' }, h('div', { class: 'flow-main' }, body, nav), aside));
  valid(index).catch(() => { index = 0; }).then(() => { if (!disposed) render(); });
  return () => { disposed = true; version++; document.removeEventListener('click', leave); cleanup.forEach(fn => fn()); };
}

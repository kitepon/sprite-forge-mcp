import { API } from './api.js?v=studio-2';
import { h, icon, picture, notice, link, dateText } from './ui.js?v=studio-2';

export const intentCaption = job => job?.kind === 'intent' ? ({ draft: '原文を保存済み・未解釈', awaiting_confirmation: '解釈案の確認待ち', confirmed: '確認した条件を採用済み' }[job.status] || '') : '';
export const terminal = job => ['completed', 'success', 'failed', 'error'].includes(job?.status) || !!intentCaption(job);
export const kindLabel = kind => ({ intent: '注文の解釈', character_bible: '設定画', preview: 'プレビュー', lora_train: '学習', from_bible: 'キャラクターの一枚', image: '画風の一枚', redraw_panel: 'パネルの描き直し', sprite: 'スプライト', transparent: '背景を透過', pixelize: 'ドットに整える', refine: '描き直し', variant: 'バリエーション' }[kind] || '画像の処理');
export function imagePaths(job = {}) {
  const paths = [job.sheet_path, job.path, ...(job.pictures || []).map(p => typeof p === 'string' ? p : p.path), ...(job.candidates || []).map(p => p.path)];
  return [...new Set(paths.filter(Boolean))];
}
export function progress(job) {
  if (job?.kind === 'lora_train' && job.progress?.total > 0) return { value: job.progress.step, total: job.progress.total, unit: 'step' };
  if (job?.kind === 'character_bible' && job.total_panels) return { value: job.completed_panels || 0, total: job.total_panels, unit: 'パネル' };
  if (job?.kind === 'preview' && job.total_images) return { value: job.pictures?.length || 0, total: job.total_images, unit: '枚' };
  return null;
}
export function matches(job, spec) { return Object.entries(spec).every(([key, value]) => job[key] === value); }
export function discoverJob(jobs, spec, baseline) {
  const candidates = jobs.filter(job => !baseline.includes(job.job_id) && matches(job, spec));
  return candidates.length === 1 ? candidates[0] : null;
}
const storageKey = 'sprite-forge.operations.v1';
export const operations = new Map(JSON.parse(localStorage.getItem(storageKey) || '[]'));
for (const op of operations.values()) {
  if (op.requesting && !terminal(op.job)) op.error = 'ページの再読み込み後、保存された制作状況を確認しています';
  op.requesting = false;
}
export let jobs = [];
export let connectionError = '';
const listeners = new Set(); let inflight;
function emit() { for (const listener of listeners) listener(); }
function save() { localStorage.setItem(storageKey, JSON.stringify([...operations].slice(-30))); }
export function subscribe(callback) { listeners.add(callback); callback(); return () => listeners.delete(callback); }
export function refreshJobs() {
  if (inflight) return inflight;
  inflight = API.jobs().then(data => {
    jobs = data; connectionError = '';
    for (const op of operations.values()) {
      const found = op.job?.job_id ? jobs.find(job => job.job_id === op.job.job_id) : discoverJob(jobs, op.spec, op.baseline);
      if (found) { op.job = found; if (terminal(found)) op.error = ''; }
    }
    save(); emit();
  }).catch(error => { connectionError = error.message; emit(); }).finally(() => { inflight = null; });
  return inflight;
}
export function startJobUpdates() { refreshJobs(); const timer = setInterval(refreshJobs, 2500); return () => clearInterval(timer); }
export function operationKey(spec) { return JSON.stringify(Object.entries(spec).sort()); }
export function active(op) { return !!op && (!terminal(op.job) && (op.requesting || !!op.job) || op.requesting); }
export async function runJob(spec, title, request) {
  const key = operationKey(spec);
  if (active(operations.get(key))) return;
  // Snapshot before the POST so an old running job cannot become this operation's progress.
  await refreshJobs();
  if (connectionError) { notice(`開始前に接続を確認できませんでした: ${connectionError}`, true); return; }
  if (active(operations.get(key))) return;
  const op = { spec, title, baseline: jobs.map(job => job.job_id), startedAt: new Date().toISOString(), requesting: true, job: null, error: '' };
  operations.set(key, op); save(); emit();
  let submitted = false;
  try {
    const response = request(); submitted = true;
    op.job = await response;
    notice(terminal(op.job) && op.job.status !== 'completed' ? `${title}でエラーが発生しました` : `${title}ができました`, op.job.status === 'failed');
  } catch (error) {
    op.error = error.message;
    op.notStarted = !submitted;
    await refreshJobs();
    notice(!submitted ? error.message : op.job?.status === 'failed' ? `${title}に失敗しました: ${error.message}` : `応答を受け取れませんでした。制作状況をご確認ください: ${error.message}`, true);
  } finally { op.requesting = false; save(); emit(); refreshJobs(); }
  return op.job;
}
export function jobView(job, { title, startedAt, error, requesting, notStarted, hideImages } = {}) {
  const failed = ['failed', 'error'].includes(job?.status);
  const done = ['completed','success'].includes(job?.status) || !!intentCaption(job); const p = progress(job);
  const caption = intentCaption(job) || (done ? 'できました' : failed ? '処理に失敗しました' : notStarted ? '入力を確認してください' : job?.kind === 'intent' ? '画像と注文を解釈しています' : job?.status === 'queued' ? '準備・GPU の処理待ち' : job ? '最後の報告：処理中' : requesting ? '開始の応答を待っています' : '応答を確認してください');
  const elapsed = startedAt && !done && !failed && !notStarted ? h('span', { class: 'elapsed', 'data-started': startedAt }) : null;
  const view = h('section', { class: `job-view ${failed ? 'failed' : done ? 'completed' : ''}` },
    h('div', { class: 'job-heading' }, h('span', { class: `job-symbol ${done || failed ? '' : 'working'}` }, icon(done ? 'check' : failed ? 'activity' : 'spark', 24)), h('div', {}, h('strong', {}, title || `${job?.name || job?.style || ''} ${kindLabel(job?.kind)}`), h('p', { class: 'muted', role: 'status' }, caption)), elapsed),
    p ? h('div', { class: 'progress-wrap' }, h('progress', { max: p.total, value: p.value, 'aria-label': '制作の進捗' }), h('span', {}, `${p.value} / ${p.total} ${p.unit}`)) : !done && !failed && !notStarted ? h('div', { class: 'indeterminate', 'aria-label': '処理待ち。進捗率は未取得' }, h('span')) : null,
    failed || notStarted ? h('p', { class: 'error-text' }, job?.error || error || '詳しいエラーは記録されていません。') : error ? h('p', { class: 'error-text' }, `通信の応答を確認できません: ${error}。生成の失敗とは限りません。`) : null,
    !done && !failed && !notStarted ? h('p', { class: 'muted small' }, job?.kind === 'intent' ? '原文は保存されています。解釈案ができたら、注文を入力した工程で確認できます。' : job?.kind === 'lora_train' ? '学習出力の実測値を表示します。この画面を離れても「制作状況」で確認できます。' : 'できた画像からここに並びます。画面を移動しても「制作状況」で確認できます。') : null,
    job?.updated_at ? h('p', { class: 'muted small' }, `最終更新 ${dateText(job.updated_at)}`) : job ? h('p', { class: 'muted small' }, '過去の記録には更新日時がありません。表示は最後に保存された状態です。') : null);
  const paths = hideImages ? [] : imagePaths(job || {});
  if (paths.length) view.append(h('div', { class: `result-grid ${job?.sheet_path ? 'with-sheet' : ''}` }, paths.map((path, index) =>
    h('figure', {}, picture(path, `${title || kindLabel(job?.kind)} ${index + 1}`, { version: job?.updated_at || job?.job_id }),
      h('figcaption', {}, paths.length > 1 ? `候補 ${index + 1}` : 'クリックで拡大', link([icon('download', 15), '保存'], API.file(path), 'text-link'))))));
  if (!done && job?.panels?.length) view.append(h('div', { class: 'panel-progress' }, job.panels.map((path, index) => picture(path, `完成パネル ${index + 1}`))));
  if (done && job?.kind === 'lora_train') view.append(h('p', {}, '画像で確かめる準備ができました。次のプレビューへ進んでください。'));
  return view;
}
export function taskPanel(spec, title, startLabel, request, cleanup, onComplete, options = {}) {
  const key = operationKey(spec); const output = h('div'); let signature = ''; let seen;
  const start = h('button', { type: 'button', class: 'primary', onclick: () => runJob(spec, title, request) }, icon('spark'), startLabel);
  const root = h('div', { class: 'task-panel stack' }, h('div', { class: 'actions' }, start, link('制作状況を見る', '#/activity', 'text-link')), output);
  cleanup.push(subscribe(() => {
    const op = operations.get(key); start.disabled = active(op); start.textContent = active(op) ? `${title}を処理中` : startLabel;
    const next = JSON.stringify(op);
    if (next !== signature) { signature = next; output.replaceChildren(...(op ? [jobView(op.job, { ...op, hideImages: options.hideCompletedImages && op.job?.status === 'completed' })] : [])); }
    if (op?.job?.status === 'completed' && seen !== op.job.job_id) { seen = op.job.job_id; onComplete?.(op.job); }
  }));
  return root;
}
export function tickElapsed(root = document) {
  for (const node of root.querySelectorAll('[data-started]')) {
    const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(node.dataset.started)) / 1000));
    node.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} 経過`;
  }
}

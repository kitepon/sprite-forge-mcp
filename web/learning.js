import { API } from './api.js?v=studio-2';
import { h, field, button, picture, notice } from './ui.js?v=studio-2';
import { referenceNotes, commentEditor, flushCaptions } from './intent.js?v=studio-2';
import { subscribe, jobs, refreshJobs, jobView, connectionError } from './jobs.js?v=studio-2';
import { trainingMaterials } from './training.js?v=studio-2';
import { draft, saveDraft } from './drafts.js?v=studio-2';

export async function learning(target, kind, name, cleanup, changed) {
  const rec = await (kind === 'character' ? API.character(name) : API.style(name));
  let busy = false, disposed = false, signature = '', version = 0;
  const summary = h('div', { class: 'learning-summary stack' }, h('strong', {}, `${rec.samples.length} 枚の画像から学習します`),
    h('div', { class: 'learning-images' }, rec.samples.map((s, i) => h('figure', {}, picture(s.path, `参考画像 ${i + 1}`), h('figcaption', {}, `画像 ${i + 1}`)))),
    rec.samples.some(s => s.caption) ? h('div', { class: 'stack small' }, rec.samples.map((s, i) => s.caption ? h('p', {}, h('strong', {}, `画像 ${i + 1}：`), s.caption) : null)) : null,
    h('p', { class: 'muted small' }, '画像の読み取りと教材の準備は自動です。希望の解釈に確認が必要なときだけお聞きします。'));
  target.append(summary);
  const notes = await referenceNotes(target, { name, kind });
  const history = await API.commentIntents(name, kind);
  const oldNote = history.find(j => j.stage === 'training' && j.learning_steps === undefined)?.original_comment;
  let legacy;
  if (oldNote) {
    const more = h('details', {}, h('summary', {}, '以前の学習への補足も引き継ぎます'));
    legacy = await referenceNotes(more, { name, kind, stage: 'training' }); target.append(more);
  }
  const key = `${kind}:${name}:steps`;
  const steps = h('input', { type: 'number', min: 1, step: 1, value: draft(key, '1200'), oninput: e => saveDraft(key, e.target.value) });
  const output = h('div', { class: 'stack', 'aria-live': 'polite' });
  const save = async () => { await flushCaptions(kind, name); await notes.save(); await legacy?.save(); };
  const execute = async request => {
    if (busy) return;
    busy = true; paint();
    try { await save(); await request(); }
    catch (error) { notice(`学習の応答を確認できませんでした：${error.message}。保存された制作状況を確認します。`, true); }
    finally { busy = false; await refreshJobs(); paint(); }
  };
  const start = button(rec.lora_name ? '今の画像でもう一度学習する' : '学習を始める', () => execute(() => {
    if (!steps.reportValidity()) throw new Error('学習ステップを確認してください。');
    return API.startLearning(name, kind, Number(steps.value));
  }));
  const actions = h('div', { class: 'actions' }, start);
  const repeat = h('details', {}, h('summary', {}, '学習をやり直す'));
  target.append(actions, output, repeat,
    h('details', { class: 'advanced' }, h('summary', {}, '詳細設定・学習の記録'), field('学習ステップ', steps),
      rec.train_job ? trainingMaterials(jobs.find(j => j.job_id === rec.train_job), '前回学習した教材') : null));
  function paint() {
    if (disposed) return;
    const candidates = jobs.filter(j => j.record_kind === kind && j.record_key === rec.key && j.record_created === rec.created);
    const parent = candidates.find(j => j.learning_steps !== undefined);
    const child = parent?.training_job_id ? jobs.find(j => j.job_id === parent.training_job_id) : candidates.find(j => j.kind === 'lora_train' && ['queued', 'running'].includes(j.status));
    const running = parent?.status === 'running' || child && ['queued', 'running'].includes(child.status);
    const oldReview = parent?.status === 'awaiting_confirmation' && !parent.proposal?.training_samples && !child;
    const reviewing = parent?.status === 'awaiting_confirmation' && !!parent.proposal?.training_samples && !child;
    const failed = parent?.status === 'failed' || child?.status === 'failed';
    const complete = child?.status === 'completed' || !!rec.lora_name;
    const repeating = complete && !busy && !running && !reviewing;
    repeat.hidden = !repeating;
    (repeating ? repeat : actions).append(start);
    actions.hidden = repeating;
    start.disabled = busy || !!running;
    start.textContent = busy || running ? '学習の準備・実行中' : reviewing ? '希望を修正して読み取り直す' : complete ? '今の画像でもう一度学習する' : '学習を始める';
    if (reviewing) start.className = 'quiet'; else start.className = '';
    notes.input.disabled = busy || !!running;
    if (legacy) legacy.input.disabled = busy || !!running;
    changed(!!complete && !busy && !running && !reviewing, busy || running ? '学習が終わるとプレビューへ進めます。' : reviewing ? '読み取った希望を確認してください。' : complete ? '' : '「学習を始める」を押してください。');
    const next = JSON.stringify([parent, child, busy, connectionError]);
    if (signature === next) return;
    signature = next; const current = ++version;
    output.replaceChildren();
    if (connectionError) output.append(h('p', { class: 'error-text' }, `制作状況を更新できません：${connectionError}`));
    if (busy && !running) output.append(h('div', { class: 'layout-waiting', role: 'status' }, h('strong', {}, '学習の開始を確認しています'), h('p', {}, '画像と希望を保存して処理を始めます。進捗が届くとここに表示します。')));
    else if (child) {
      output.append(jobView(child, { title: '学習', startedAt: child.created_at }), h('details', {}, h('summary', {}, '学習する画像と説明を見る'), trainingMaterials(child)));
    } else if (running) output.append(jobView(parent, { title: '画像と希望を読み取っています', startedAt: parent.created_at }));
    else if (reviewing) {
      const review = h('div'); output.append(review);
      commentEditor(review, { name, kind, stage: 'training', learningJob: parent,
        onLearningConfirm: proposal => execute(() => API.confirmLearning(parent.job_id, proposal)) }).then(() => {
        if (disposed || current !== version) review.remove();
      }).catch(error => { if (!disposed && current === version) notice(error.message, true); });
    } else if (oldReview) output.append(h('p', {class:'muted small'}, '保存した画像と希望を引き継ぎます。「学習を始める」で、画像ごとの使い方を確認して学習へ進みます。'));
    else if (failed) output.append(jobView(parent, { title: '学習の準備' }));
    else if (complete) output.append(h('p', { class: 'callout' }, '学習済みです。次のプレビューで顔や体形、衣装を確かめられます。'));
  }
  cleanup.push(() => { disposed = true; version++; });
  cleanup.push(subscribe(paint));
  await refreshJobs();
  paint();
  return save;
}

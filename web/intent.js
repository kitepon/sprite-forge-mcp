import { API } from './api.js?v=studio-2';
import { h, field, button, picture, action, notice, dateText } from './ui.js?v=studio-2';
import { draft, saveDraft, clearDraft } from './drafts.js?v=studio-2';
import { subscribe, jobs, connectionError } from './jobs.js?v=studio-2';
import { trainingSelection } from './training.js?v=studio-2';

const features = { face: '顔', hair: '髪', outfit: '衣装', style: '描き方', expression: '表情', pose: '姿勢・向き', accessory: '小物', background: '背景', subject: '被写体', composition: '構図', lighting: '光' };
const scopes = { persistent: '今後も共通', this_run: '今回だけ', panel: 'このパネルに残す' };
const captionSaves = new Map();

export function savedLearningExplanation(job) {
  const proposal = job.accepted || job.proposal;
  const source = ref => ref ? `画像 ${job.references.findIndex(r => r.sample_index === ref.sample_index && r.path === ref.path) + 1}` : '';
  const observations = job.accepted_observations || proposal.observations;
  return h('section', { class: 'intent-editor stack' }, h('h3', {}, 'AIが読み取った内容'),
    h('p', { class: 'muted small' }, `${job.created_at ? dateText(job.created_at) + ' · ' : ''}${job.accepted ? '採用済みの内容' : '保存されている解釈案・未採用'}`),
    h('details', {}, h('summary', {}, 'この時の注文を見る'), h('p', {}, job.original_comment || '全体への注文なし')),
    proposal.training_samples ? trainingSelection(proposal.training_samples, job.references) : null,
    proposal.changes.map(change => h('article', { class: 'intent-change stack' },
      h('div', { class: 'section-heading' }, h('strong', {}, features[change.feature]), h('span', { class: 'badge' }, scopes[change.scope])),
      change.reference ? h('p', { class: 'muted small' }, `${features[change.feature]}の参照元：${source(change.reference)}`) : null,
      h('p', {}, change.reason_ja), change.avoid_ja ? h('p', {}, `避ける内容：${change.avoid_ja}`) : null,
      change.description_en || change.avoid_en ? h('details', {}, h('summary', {}, '生成文の詳細'),
        h('pre', { class: 'training-caption' }, change.description_en), change.avoid_en ? h('pre', { class: 'training-caption' }, change.avoid_en) : null) : null)),
    proposal.questions.length ? h('div', { class: 'callout' }, h('strong', {}, 'この時の確認事項'), proposal.questions.map(q => h('p', {}, q))) : null,
    observations.length ? h('section', { class: 'stack' }, h('h3', {}, '画像ごとの読み取り'),
      h('div', { class: 'sample-grid training-grid' }, observations.map(item => h('article', { class: 'sample-card' },
        picture(item.reference.path, `${source(item.reference)}の読み取り`), h('div', { class: 'sample-content stack' },
          h('strong', {}, source(item.reference)), h('p', {}, item.appearance_ja),
          h('details', {}, h('summary', {}, '教材の説明（英語）'), h('pre', { class: 'training-caption' }, item.caption_en))))))) : null);
}

export function saveCaption(kind, name, sample, value) {
  const key = `${kind}:${name}:caption:${sample.index}:${sample.path}`;
  const previous = captionSaves.get(key) || Promise.resolve();
  const request = previous.catch(() => {}).then(async () => {
    await (kind === 'character' ? API.setCaption : API.setStyleCaption)(name, sample.index, value);
    if (draft(key, sample.caption || '') === value) clearDraft(key);
  });
  captionSaves.set(key, request);
  const finish = () => { if (captionSaves.get(key) === request) captionSaves.delete(key); };
  request.then(finish, finish);
  return request;
}

export async function flushCaptions(kind, name) {
  const record = await (kind === 'character' ? API.character(name) : API.style(name));
  for (const sample of record.samples) {
    const key = `${kind}:${name}:caption:${sample.index}:${sample.path}`;
    const value = draft(key, sample.caption || '');
    if (value === (sample.caption || '')) continue;
    await saveCaption(kind, name, sample, value);
  }
}

export async function referenceNotes(target, { name, kind, stage = 'samples' }) {
  const key = `intent:${kind}:${name}:${stage}:`;
  const history = await API.commentIntents(name, kind);
  const prior = history.find(j => j.stage === stage && !j.panel && j.learning_steps === undefined);
  let saved = prior?.original_comment || '';
  const input = h('textarea', { rows: 3, 'aria-label': stage === 'samples' ? '画像から採用したい特徴' : '学習への補足', placeholder: '例：2枚目から顔立ち、4枚目から体形と衣装を採用してほしい。' }, draft(key, saved));
  const status = h('p', { class: 'draft-status', role: 'status' }, '任意です。入力した希望は自動で保存します。');
  let saving = Promise.resolve();
  const save = () => {
    saving = saving.catch(() => {}).then(async () => {
    const value = input.value;
    if (value === saved) return;
    status.textContent = '希望を保存しています…';
    try {
      await API.saveComment({ name, kind, stage, panel: '', comment: value });
      saved = value;
      if (input.value === value) { clearDraft(key); status.textContent = '保存済み'; }
    } catch (error) { status.textContent = `保存できませんでした：${error.message}`; throw error; }
    });
    return saving;
  };
  input.addEventListener('input', () => { saveDraft(key, input.value); status.textContent = '入力中・移動する前に保存します'; });
  input.addEventListener('blur', () => save().catch(error => notice(error.message, true)));
  target.append(field(stage === 'samples' ? '画像から採用したい特徴（任意）' : '学習への補足（任意）', input, '画像ごとの希望と一緒に、学習を始めるときに読み取ります。'), status);
  return { save, input };
}

export async function commentEditor(target, { name, kind, stage, panel = '', interpretEnabled = true, learningJob = null, learningActions = null, onLearningConfirm = null, cleanup = [] }) {
  const key = `intent:${kind}:${name}:${stage}:${panel}`;
  let job = null, savedText = '', busy = false, saveVersion = 0;
  const input = h('textarea', { rows: 3, placeholder: stage === 'preview' ? '例：参考画像の顔と髪を保って、横向きの全身像を描いて。' : '例：4枚目の衣装を今後も使って。顔と髪はそのままで。', 'aria-label': '制作への注文' });
  const status = h('p', { class: 'draft-status', role: 'status' });
  const output = h('div', { class: 'intent-proposal stack' });
  const titles = { preview: '顔や衣装の調整', drawing: '描きたい内容', sheet: '設定画全体への希望', panel: 'このパネルの修正', samples: '画像から採用したい特徴', training: '読み取った希望の確認' };
  const box = h('section', { class: 'intent-editor stack' }, h('h3', {}, titles[stage]), h('span', { class: 'badge' }, '研究中の機能'), h('p', { class: 'muted small' }, learningJob ? '希望の解釈を確認してください。画像の説明と希望を保存し、続けて学習を始めます。' : '希望を読み取り、確認してから反映します。十分に反映されない場合は生成画像を見て調整してください。'), learningJob ? null : field('制作への注文', input, '日本語で書けます。'), status);
  input.addEventListener('input', () => { saveDraft(key, input.value); status.textContent = input.value === savedText ? '原文は保存済み' : '未保存の変更があります'; });
  const paint = (edits = null) => {
    output.replaceChildren();
    status.textContent = busy ? '原文を保存しました。画像と注文を解釈しています…' : ({ draft: '原文を保存しました。まだ解釈していません', running: '解釈中です。画面を開き直して結果を確認できます', awaiting_confirmation: '解釈案ができました。内容を確かめてください', confirmed: '採用済みです', failed: '解釈できませんでした。原文は保存されています' }[job?.status] || '注文は、この工程を離れる前にも保存します');
    if (job?.status === 'confirmed' && job.accepted.changes.some(c => c.style_deferred)) status.textContent = '画風の希望は今回反映していません。ほかの希望は採用済みです。';
    if (input.value !== savedText) status.textContent = '未保存の変更があります';
    if (!job) return;
    if (busy || job.status === 'running') {
      output.append(h('div', { class: 'layout-waiting', role: 'status' }, h('strong', {}, '希望を読み取っています'), h('span', { class: 'elapsed', 'data-started': job.created_at || new Date().toISOString() }),
        h('p', {}, '完了すると確認内容をここに表示します。'), connectionError ? h('p', { class: 'error-text' }, `状況を更新できません：${connectionError}`) : null));
      return;
    }
    if (job.error) output.append(h('p', { class: 'error-text' }, job.error));
    if (job.references.length && !learningJob) output.append(h('details', {}, h('summary', {}, '参照した画像'), h('div', { class: 'intent-references' }, job.references.map((ref, index) => h('figure', {}, picture(ref.path, `注文時の画像 ${index + 1}`, { plain: true }), h('figcaption', {}, `注文時の画像 ${index + 1}`))))));
    const proposal = structuredClone(job.accepted || edits?.proposal || job.proposal);
    if (!proposal) return;
    const learningStage = ['samples', 'training'].includes(stage);
    if (learningStage && proposal.training_samples) output.append(trainingSelection(proposal.training_samples, job.references));
    if (proposal.questions.length) output.append(h('div', { class: 'callout stack' }, h('strong', {}, 'ここを教えてください'), proposal.questions.map(question => h('p', {}, question)), h('p', { class: 'muted small' }, learningJob ? '上の「画像から採用したい特徴」に回答を追記し、「希望を修正して読み取り直す」を押してください。' : '上の注文へ回答を書き足して、もう一度読み取ってください。')));
    for (const change of proposal.changes) {
      const sourceIndex = change.reference ? job.references.findIndex(ref => ref.record_key === change.reference.record_key && ref.sample_index === change.reference.sample_index && ref.path === change.reference.path) : -1;
      const source = sourceIndex >= 0 ? [h('p', {class:'muted small'}, `${features[change.feature]}の参照元：画像 ${sourceIndex + 1}`)] : [];
      if (change.feature === 'style') {
        if (learningStage) {
          output.append(h('article', {class:'intent-change stack'}, h('strong', {}, '素材から学ぶ画風'), ...source, h('p', {}, change.reason_ja)));
          continue;
        }
        const disabled = job.status === 'confirmed';
        const scope = h('select', { disabled, 'aria-label': '画風の適用範囲', onchange: e => {
          change.scope = e.target.value; change.panel_key = null;
        } }, Object.entries(scopes).filter(([value]) => value !== 'panel').map(([value, label]) => h('option', {value, selected: value === change.scope}, label)));
        const selected = h('select', { disabled: disabled || kind === 'style', 'aria-label': '他の画風を使いたい場合はこちらから選択', onchange: e => {
          change.style_name = JSON.parse(e.target.value); change.style_deferred = false;
          paint({proposal, observations});
        } }, h('option', { value: 'null' }, '選択してください'),
          ...(stage !== 'panel' || !job.existing_settings?.sheet_style ? [h('option', { value: '""' }, '追加の画風を使わない（キャラクターの画風を使う）')] : []),
          (job.available_styles || []).filter(s => stage !== 'panel' || s.name === job.existing_settings?.sheet_style).map(s => h('option', { value: JSON.stringify(s.name) }, s.name)));
        selected.value = JSON.stringify(change.style_name ?? null);
        const defer = h('input', { type: 'checkbox', checked: !!change.style_deferred, disabled, 'aria-label': '今回は画風の希望を反映しない', onchange: e => {
          change.style_deferred = e.target.checked;
          if (change.style_deferred) change.style_name = null;
          paint({proposal, observations});
        } });
        output.append(h('article', {class:'intent-change stack'}, h('div', {class:'section-heading'}, h('strong', {}, '画風'), scope),
          ...source, h('p', {}, change.reason_ja),
          ...(kind === 'character' ? [field('他の画風を使いたい場合はこちらから選択', selected, stage === 'panel' ? '元のシートと同じ画風だけ選べます。' : '登録済みの画風を追加できます。一つのシートの画風は統一します。')] : []),
          ...(stage === 'panel' ? [h('p', {class:'muted small'}, '部分描き直しは元のシートの画風を維持します。画風を変える時は、設定画全体の注文から指定してください。')] : []),
          ...(kind === 'style' ? [h('p', {class:'muted small'}, 'この画風自体を変える希望は、素材と学習の工程で確認してください。')] : []),
          h('label', { class: 'intent-defer' }, defer, h('span', {}, '今回は画風の希望を反映しない')),
          h('p', {class:'muted small'}, `チェックすると現在の画風設定（${job.existing_settings?.[stage === 'panel' ? 'sheet_style' : 'style'] || '追加の画風なし'}）を変えず、ほかの希望だけを採用します。画風の希望は履歴に残りますが、後から自動で反映されることはありません。`)));
        continue;
      }
      const panelSpecs = job.panel_specs || [];
      const targetPanel = h('select', { disabled: job.status === 'confirmed' || change.scope === 'persistent', 'aria-label': `${features[change.feature]}の対象パネル`, onchange: e => { change.panel_key = e.target.value || null; } });
      const paintTargets = () => {
        targetPanel.disabled = job.status === 'confirmed' || change.scope === 'persistent';
        targetPanel.replaceChildren(...(change.scope === 'panel' ? [] : [h('option', { value: '', selected: !change.panel_key }, '設定画全体')]),
          ...panelSpecs.map(p => h('option', { value: p.key, selected: p.key === change.panel_key }, `${p.section} · ${p.label}`)));
      };
      const scope = h('select', { disabled: job.status === 'confirmed', 'aria-label': `${features[change.feature]}の適用範囲`, onchange: e => {
        change.scope = e.target.value;
        if (change.scope === 'persistent') change.panel_key = null;
        else if (change.scope === 'panel') change.panel_key ||= panel || panelSpecs[0]?.key;
        paintTargets();
      } }, Object.entries(scopes).filter(([value]) => value !== 'panel' || ['sheet', 'panel'].includes(stage)).map(([value, label]) => h('option', { value, selected: value === change.scope }, label)));
      paintTargets();
      const positive = h('textarea', { rows: 2, disabled: job.status === 'confirmed', 'aria-label': `${features[change.feature]}の生成文`, oninput: e => { change.description_en = e.target.value; } }, change.description_en);
      const negative = h('input', { value: change.avoid_en, disabled: job.status === 'confirmed', 'aria-label': `${features[change.feature]}で避ける内容`, oninput: e => { change.avoid_en = e.target.value; } });
      const negativeJa = h('input', { value: change.avoid_ja || '', disabled: job.status === 'confirmed', 'aria-label': `${features[change.feature]}で避ける内容の日本語`, oninput: e => { change.avoid_ja = e.target.value; } });
      output.append(h('article', { class: 'intent-change stack' }, h('div', { class: 'section-heading' }, h('strong', {}, features[change.feature]), h('span', { class: 'badge' }, scopes[change.scope])), ...source, h('p', {}, change.reason_ja), change.avoid_ja ? h('p', { class: 'muted small' }, `避ける内容：${change.avoid_ja}`) : null, h('details', {}, h('summary', {}, '解釈の詳細を編集'), field('適用範囲', scope), ...(stage === 'sheet' ? [field('対象', targetPanel)] : []), field('避ける内容（日本語）', negativeJa), field('採用する内容（英語）', positive), field('避ける内容（英語）', negative))));
    }
    const observations = structuredClone(job.accepted_observations || edits?.observations || proposal.observations);
    if (['samples', 'training'].includes(stage) && observations.length) {
      const observed = h('section', { class: 'stack' }, h('h3', {}, '画像に写っている事実・教材の説明'), h('p', { class: 'muted small' }, '希望する変更は教材の説明に入れません。画像と一致する内容を確認してください。'));
      for (const item of observations) {
        const index = job.references.findIndex(ref => ref.sample_index === item.reference.sample_index);
        const disabled = !!job.accepted_observations;
        observed.append(h('article', { class: 'intent-change stack' }, h('strong', {}, `画像 ${index + 1}`), picture(item.reference.path, `教材説明の画像 ${index + 1}`),
          field('画像に見える内容', h('textarea', { rows: 3, disabled, 'aria-label': `画像 ${index + 1} の観察`, oninput: e => { item.appearance_ja = e.target.value; } }, item.appearance_ja)),
          field('学習へ渡す説明（英語）', h('textarea', { rows: 3, disabled, 'aria-label': `画像 ${index + 1} の教材説明`, oninput: e => { item.caption_en = e.target.value; } }, item.caption_en || ''))));
      }
      if (!learningJob) observed.append(job.accepted_observations ? h('p', { role: 'status' }, '教材の説明は確認済みです。学習はまだ始まりません。') : button('この画像説明を教材に採用', e => action(e.currentTarget, async () => {
        if (input.value !== savedText) throw new Error('注文が変わっています。もう一度解釈してください。');
        job = await API.confirmObservations(job.job_id, observations); paint({proposal, observations}); notice('画像の説明を教材用に保存しました。学習はまだ始まりません');
      }), 'quiet'));
      output.append(learningJob ? h('details', {}, h('summary', {}, '画像の読み取りを確認・編集'), observed) : observed);
    } else if (observations.length) output.append(h('details', {}, h('summary', {}, '画像から読み取った内容'), observations.map(item => h('p', {}, item.appearance_ja))));
    const needsStyleChoice = !learningStage && proposal.changes.some(c => c.feature === 'style' && c.style_name == null && !c.style_deferred);
    if (job.status === 'awaiting_confirmation' && needsStyleChoice) output.append(h('p', {class:'muted small', role:'status'}, '画風の希望はまだ反映できません。上の画風欄で、使う画風を選ぶか「今回は画風の希望を反映しない」を選んでください。'));
    if (learningJob && learningActions) output.append(learningActions);
    else if (learningJob && job.status === 'awaiting_confirmation' && !proposal.questions.length) {
      const confirm = button('この内容で学習を始める', e => action(e.currentTarget, () => onLearningConfirm({ ...proposal, observations })));
      confirm.disabled = needsStyleChoice;
      output.append(confirm);
    } else if (!learningJob && job.status === 'awaiting_confirmation') {
      const confirm = button('この内容を採用', e => action(e.currentTarget, async () => {
      if (input.value !== savedText) throw new Error('注文が変わっています。もう一度解釈してください。');
      job = await API.confirmComment(job.job_id, proposal); paint({proposal, observations}); notice(proposal.changes.some(c => c.style_deferred) ? '画風の希望は今回反映していません。ほかの希望は採用しました。' : '確認した条件を採用しました');
      }));
      confirm.disabled = needsStyleChoice;
      output.append(confirm);
    }
    if (job.interpreter) output.append(h('details', {}, h('summary', {}, '処理の記録'), h('p', { class: 'muted small' }, `${job.interpreter.model} · 解釈に ${job.interpreter.elapsed_seconds} 秒`)));
  };
  const save = async (force = false) => {
    const version = ++saveVersion;
    const text = input.value;
    await flushCaptions(kind, name);
    if (!force && text === savedText) return job;
    const record = await (kind === 'character' ? API.character(name) : API.style(name));
    const saved = await API.saveComment({ name, kind, stage, panel, comment: text, sample_indices: record.samples.map(s => s.index) });
    if (version !== saveVersion) return saved;
    job = saved;
    savedText = text;
    if (input.value === text) clearDraft(key);
    paint();
    return job;
  };
  if (!learningJob) box.append(h('div', { class: 'actions' }, interpretEnabled ? button('希望を読み取る', e => action(e.currentTarget, async () => {
    if (busy) return;
    const submitted = await save(true); busy = true; paint();
    try {
      const result = await API.interpretComment(submitted.job_id);
      if (job.job_id === submitted.job_id) job = result;
    } catch (error) {
      if (job.job_id === submitted.job_id) job = await API.job(submitted.job_id);
      throw error;
    } finally { busy = false; paint(); }
  })) : h('p', { class: 'muted small' }, '希望は工程を移るときに保存します。')));
  box.append(output);
  input.addEventListener('blur', () => save().catch(error => notice(error.message, true)));
  const history = learningJob ? [] : await API.commentIntents(name, kind);
  job = learningJob || history.find(item => item.stage === stage && item.panel === panel) || null;
  savedText = job?.original_comment || ''; input.value = learningJob ? savedText : draft(key, savedText); paint();
  const dispose = learningJob ? () => {} : subscribe(() => {
    if (job?.status !== 'running' || busy) return;
    const fresh = jobs.find(item => item.job_id === job.job_id);
    if (fresh) { job = fresh; paint(); }
  });
  cleanup.push(dispose);
  target.append(box);
  return { save, dispose, confirmedJob: () => {
    if (input.value !== savedText || job && job.status !== 'confirmed') throw new Error('注文を解釈して、内容を採用してから生成してください。');
    return job?.job_id || '';
  } };
}

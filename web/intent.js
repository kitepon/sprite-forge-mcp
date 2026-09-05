import { API } from './api.js?v=studio-2';
import { h, field, button, picture, action, notice } from './ui.js?v=studio-2';
import { draft, saveDraft, clearDraft } from './drafts.js?v=studio-2';

const features = { face: '顔', hair: '髪', outfit: '衣装', style: '描き方', expression: '表情', pose: '姿勢・向き', accessory: '小物', background: '背景', subject: '被写体', composition: '構図', lighting: '光' };
const scopes = { persistent: '今後も共通', this_run: '今回だけ', panel: 'このパネルに残す' };

export async function flushCaptions(kind, name) {
  const record = await (kind === 'character' ? API.character(name) : API.style(name));
  for (const sample of record.samples) {
    const key = `${kind}:${name}:caption:${sample.index}:${sample.path}`;
    const value = draft(key, sample.caption || '');
    if (value === (sample.caption || '')) continue;
    await (kind === 'character' ? API.setCaption : API.setStyleCaption)(name, sample.index, value);
    if (draft(key, sample.caption || '') === value) clearDraft(key);
  }
}

export async function commentEditor(target, { name, kind, stage, panel = '', interpretEnabled = true }) {
  const key = `intent:${kind}:${name}:${stage}:${panel}`;
  let job = null, savedText = '', busy = false, saveVersion = 0;
  const input = h('textarea', { rows: 3, placeholder: '例：4枚目の衣装を今後も使って。顔と髪はそのままで。', 'aria-label': '制作への注文' });
  const status = h('p', { class: 'draft-status', role: 'status' });
  const output = h('div', { class: 'intent-proposal stack' });
  const box = h('section', { class: 'intent-editor stack' }, h('h3', {}, '言葉で、作りたい姿へ'), h('span', { class: 'badge' }, '研究中の機能'), h('p', { class: 'muted small' }, 'コメントから生成条件を提案します。採用しても、学習済みの特徴などの影響で、衣装・向き・背景が十分に反映されない場合があります。生成画像を確認してご利用ください。'), field('制作への注文', input, '画像ごとのコメントも一緒に読みます。解釈案を確認してから採用できます。'), status);
  input.addEventListener('input', () => { saveDraft(key, input.value); status.textContent = input.value === savedText ? '原文は保存済み' : '未保存の変更があります'; });
  const paint = (edits = null) => {
    output.replaceChildren();
    status.textContent = busy ? '原文を保存しました。画像と注文を解釈しています…' : ({ draft: '原文を保存しました。まだ解釈していません', running: '解釈中です。画面を開き直して結果を確認できます', awaiting_confirmation: '解釈案ができました。内容を確かめてください', confirmed: '採用済みです', failed: '解釈できませんでした。原文は保存されています' }[job?.status] || '注文は、この工程を離れる前にも保存します');
    if (job?.status === 'confirmed' && job.accepted.changes.some(c => c.style_deferred)) status.textContent = '採用済みです。画風の希望は保留中です';
    if (input.value !== savedText) status.textContent = '未保存の変更があります';
    if (!job) return;
    if (job.error) output.append(h('p', { class: 'error-text' }, job.error));
    if (job.references.length) output.append(h('div', { class: 'intent-references' }, job.references.map((ref, index) => h('figure', {}, picture(ref.path, `注文時の画像 ${index + 1}`, { plain: true }), h('figcaption', {}, `注文時の画像 ${index + 1}`)))));
    const proposal = structuredClone(job.accepted || edits?.proposal || job.proposal);
    if (!proposal) return;
    if (proposal.questions.length) output.append(h('div', { class: 'callout stack' }, h('strong', {}, 'ここを教えてください'), proposal.questions.map(question => h('p', {}, question)), h('p', { class: 'muted small' }, '上の注文へ回答を書き足して、もう一度解釈してください。')));
    for (const change of proposal.changes) {
      const sourceIndex = change.reference ? job.references.findIndex(ref => ref.record_key === change.reference.record_key && ref.sample_index === change.reference.sample_index && ref.path === change.reference.path) : -1;
      const source = sourceIndex >= 0 ? [h('p', {class:'muted small'}, `${features[change.feature]}の参照元：画像 ${sourceIndex + 1}`)] : [];
      if (change.feature === 'style') {
        const disabled = job.status === 'confirmed';
        const scope = h('select', { disabled, 'aria-label': '画風の適用範囲', onchange: e => {
          change.scope = e.target.value; change.panel_key = null;
        } }, Object.entries(scopes).filter(([value]) => value !== 'panel').map(([value, label]) => h('option', {value, selected: value === change.scope}, label)));
        const selected = h('select', { disabled: disabled || kind === 'style', 'aria-label': '採用する画風', onchange: e => {
          change.style_name = JSON.parse(e.target.value); change.style_deferred = false;
          paint({proposal, observations});
        } }, h('option', { value: 'null' }, '未解決・画風の選択や学習が必要'),
          ...(stage !== 'panel' || !job.existing_settings?.sheet_style ? [h('option', { value: '""' }, '追加の画風を使わない（キャラクターLoRAのみ）')] : []),
          (job.available_styles || []).filter(s => stage !== 'panel' || s.name === job.existing_settings?.sheet_style).map(s => h('option', { value: JSON.stringify(s.name) }, s.name)));
        selected.value = JSON.stringify(change.style_name ?? null);
        const defer = h('input', { type: 'checkbox', checked: !!change.style_deferred, disabled, 'aria-label': '画風の希望を保留する', onchange: e => {
          change.style_deferred = e.target.checked;
          if (change.style_deferred) change.style_name = null;
          paint({proposal, observations});
        } });
        output.append(h('article', {class:'intent-change stack'}, h('div', {class:'section-heading'}, h('strong', {}, '画風'), scope),
          ...source, h('p', {}, change.reason_ja), field('シート全体に使う画風', selected, '一つのシートの画風は統一します。'),
          ...(stage === 'panel' ? [h('p', {class:'muted small'}, '部分描き直しは元のシートの画風を維持します。画風を変える時は、設定画全体の注文から指定してください。')] : []),
          ...(kind === 'style' ? [h('p', {class:'muted small'}, 'この画風自体を変える希望は、素材と学習の工程で確認してください。')] : []),
          h('label', { class: 'intent-defer' }, defer, h('span', {}, '画風の希望は保留して、ほかの注文を採用する')),
          h('p', {class:'muted small'}, '希望は原文と解釈案に残ります。新しい画風が必要なら、画風の素材・学習画面で確認してください。学習は自動では始まりません。')));
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
      output.append(h('article', { class: 'intent-change stack' }, h('div', { class: 'section-heading' }, h('strong', {}, features[change.feature]), scope), ...source, ...(stage === 'sheet' ? [field('対象', targetPanel)] : []), h('p', {}, change.reason_ja), field('避ける内容（日本語）', negativeJa, '除外するものがなければ空欄。訂正は上の注文へ書き足して再解釈できます。'), h('details', {}, h('summary', {}, '生成へ渡す言葉を確認・編集'), field('採用する内容（英語）', positive), field('避ける内容（英語）', negative))));
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
      observed.append(job.accepted_observations ? h('p', { role: 'status' }, '教材の説明は確認済みです。学習はまだ始まりません。') : button('この画像説明を教材に採用', e => action(e.currentTarget, async () => {
        if (input.value !== savedText) throw new Error('注文が変わっています。もう一度解釈してください。');
        job = await API.confirmObservations(job.job_id, observations); paint({proposal, observations}); notice('画像の説明を教材用に保存しました。学習はまだ始まりません');
      }), 'quiet'));
      output.append(observed);
    } else if (observations.length) output.append(h('details', {}, h('summary', {}, '画像から読み取った内容'), observations.map(item => h('p', {}, item.appearance_ja))));
    if (job.status === 'awaiting_confirmation') output.append(button('この内容を採用', e => action(e.currentTarget, async () => {
      if (input.value !== savedText) throw new Error('注文が変わっています。もう一度解釈してください。');
      job = await API.confirmComment(job.job_id, proposal); paint({proposal, observations}); notice(proposal.changes.some(c => c.style_deferred) ? 'ほかの条件を採用しました。画風の希望は保留中です' : '確認した条件を採用しました');
    })));
    if (job.interpreter) output.append(h('p', { class: 'muted small' }, `${job.interpreter.model} · 解釈に ${job.interpreter.elapsed_seconds} 秒`));
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
  box.append(h('div', { class: 'actions' }, button('原文を保存', e => action(e.currentTarget, () => save()), 'quiet'), interpretEnabled ? button('画像と注文を解釈する', e => action(e.currentTarget, async () => {
    if (busy) return;
    const submitted = await save(true); busy = true; paint();
    try {
      const result = await API.interpretComment(submitted.job_id);
      if (job.job_id === submitted.job_id) job = result;
    } catch (error) {
      if (job.job_id === submitted.job_id) job = await API.job(submitted.job_id);
      throw error;
    } finally { busy = false; paint(); }
  })) : h('p', { class: 'muted small' }, 'この工程は原文の保存のみ対応しています。解釈・実行への接続は準備中です。')), output);
  const history = await API.commentIntents(name, kind);
  job = history.find(item => item.stage === stage && item.panel === panel) || null;
  savedText = job?.original_comment || ''; input.value = draft(key, savedText); paint();
  target.append(box);
  return { save, confirmedJob: () => {
    if (input.value !== savedText || job && job.status !== 'confirmed') throw new Error('注文を解釈して、内容を採用してから生成してください。');
    return job?.job_id || '';
  } };
}

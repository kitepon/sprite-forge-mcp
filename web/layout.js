import { API } from './api.js?v=studio-2';
import { h, field, button, action, picture } from './ui.js?v=studio-2';
import { draft, saveDraft, clearDraft } from './drafts.js?v=studio-2';
import { flushCaptions } from './intent.js?v=studio-2';

const features = { subject: '被写体・体形・体色', face: '顔', hair: '髪', outfit: '衣装', expression: '表情', pose: '姿勢・向き', accessory: '小物', composition: '構図', background: '背景', lighting: '光' };
export const layoutValues = panels => panels.map(({ description_ja, reference, ...value }) => value);
const describe = panels => panels.map(p => ({ ...structuredClone(p), description_ja: p.label, reference: null }));
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));

export async function layoutEditor(target, name) {
  const storageKey = `layout:${name}`;
  let saved = await API.sheetLayout(name);
  let job = (await API.commentIntents(name, 'character')).find(j => j.stage === 'layout') || null;
  if (job?.status === 'discarded') job = null;
  let proposal = structuredClone(job?.accepted || job?.proposal || { summary_ja: '', questions: [], panels: describe(saved) });
  if (job?.status === 'confirmed' && !same(job.confirmed_layout, saved)) {
    job = null; proposal = { summary_ja: '', questions: [], panels: describe(saved) };
  }
  let original = job?.original_comment || '', busy = false;
  const stored = draft(storageKey, null);
  const cached = stored?.jobId === (job?.job_id || null) ? stored : null;
  if (cached) proposal = cached.proposal;
  let conflict = !!cached && !same(cached.expected, saved);
  const input = h('textarea', { rows: 3, 'aria-label': 'シート構成への注文', placeholder: '載せたい項目や変更したい内容を書いてください。' });
  input.value = cached?.text ?? original;
  const status = h('p', { role: 'status', class: 'draft-status' });
  const list = h('div', { class: 'layout-list' });
  const explanation = h('div', { class: 'stack' });
  const controls = h('fieldset', { class: 'layout-controls' });
  const changed = () => !same(layoutValues(proposal.panels), saved);
  const remember = () => { saveDraft(storageKey, { jobId: job?.job_id || null, text: input.value, proposal, expected: conflict ? cached.expected : saved }); showStatus(); };
  const showStatus = () => {
    status.textContent = conflict ? '保存済み構成が別の操作で更新されています。下書きと比較し、最新の構成を読み込んでください。' : busy ? '構成案を考えています。原文は保存済みです。' : job?.status === 'running' ? '構成案を考えています。再表示で結果を確認できます。' : input.value !== original ? '注文に未解釈の変更があります' : job?.status === 'awaiting_confirmation' || changed() ? '構成はまだ確定していません' : '保存した構成を次の生成に使います';
  };
  input.addEventListener('input', remember);
  const editInput = (label, value, write, multiline = false) => {
    const control = h(multiline ? 'textarea' : 'input', { 'aria-label': label, ...(multiline ? { rows: 2 } : {}), oninput: e => { write(e.target.value); remember(); } });
    control.value = value; return field(label, control);
  };
  const paint = () => {
    list.replaceChildren(); explanation.replaceChildren();
    if (proposal.summary_ja) explanation.append(h('p', {}, proposal.summary_ja));
    if (job?.error) explanation.append(h('p', { class: 'error-text' }, job.error));
    if (proposal.questions.length) explanation.append(h('div', { class: 'callout' }, h('strong', {}, '構成について確認したいこと'), proposal.questions.map(q => h('p', {}, q)), h('p', {}, '上の注文へ回答を書き足して、もう一度構成案を作ってください。')));
    proposal.panels.forEach((panel, index) => {
      const move = offset => { const next = index + offset; [proposal.panels[index], proposal.panels[next]] = [proposal.panels[next], proposal.panels[index]]; remember(); paint(); };
      const up = button('↑', () => move(-1), 'quiet'); up.disabled = index === 0; up.setAttribute('aria-label', `${panel.label}を上へ`);
      const down = button('↓', () => move(1), 'quiet'); down.disabled = index === proposal.panels.length - 1; down.setAttribute('aria-label', `${panel.label}を下へ`);
      const details = h('details', {}, h('summary', {}, '描く内容を確認・編集'));
      const parts = h('div', { class: 'stack' });
      const roles = h('div', { class: 'stack' });
      const paintParts = () => {
        parts.replaceChildren(...panel.parts.map((part, partIndex) => {
          const select = h('select', { 'aria-label': `${panel.label}の特徴 ${partIndex + 1}`, onchange: e => {
            const before = part.feature, hadRole = panel.role_features.includes(before); part.feature = e.target.value;
            if (!panel.parts.some(p => p.feature === before)) panel.role_features = panel.role_features.filter(f => f !== before);
            if (hadRole && !panel.role_features.includes(part.feature)) panel.role_features.push(part.feature);
            remember(); paintParts();
          } }, Object.entries(features).map(([value, label]) => h('option', { value, selected: value === part.feature }, label)));
          return h('div', { class: 'layout-part stack' }, select,
            editInput(`${panel.label}の${features[part.feature]}（英語）`, part.description_en, value => { part.description_en = value; }, true),
            editInput(`${panel.label}で避ける${features[part.feature]}（英語）`, part.avoid_en, value => { part.avoid_en = value; }),
            button('この特徴を外す', () => { panel.parts.splice(partIndex, 1); if (!panel.parts.some(p => p.feature === part.feature)) panel.role_features = panel.role_features.filter(f => f !== part.feature); remember(); paintParts(); }, 'quiet'));
        }));
        roles.replaceChildren(h('p', { class: 'muted small' }, '共通条件より、この項目の指定を優先する特徴'), ...[...new Set(panel.parts.map(part => part.feature))].map(feature => field(features[feature], h('input', {
          type: 'checkbox', checked: panel.role_features.includes(feature), 'aria-label': `${panel.label}の${features[feature]}を項目固有にする`,
          onchange: e => { panel.role_features = panel.role_features.filter(f => f !== feature); if (e.target.checked) panel.role_features.push(feature); remember(); }
        }))));
      };
      paintParts();
      const kind = h('select', { 'aria-label': `${panel.label}の画像種別`, onchange: e => { panel.kind = e.target.value; remember(); } }, Object.entries({ full: '全身', face: '顔中心', item: '単品', chibi: '小さな全身' }).map(([value, label]) => h('option', { value, selected: value === panel.kind }, label)));
      details.append(field('画像種別', kind), parts, button('特徴を追加', () => { panel.parts.push({ feature: 'subject', description_en: '', avoid_en: '' }); remember(); paintParts(); }, 'quiet'), roles, h('p', { class: 'muted small' }, '共通条件を受け継ぐ特徴'),
        ...Object.entries(features).map(([feature, label]) => field(label, h('input', { type: 'checkbox', checked: panel.inherited_features.includes(feature), onchange: e => { panel.inherited_features = panel.inherited_features.filter(f => f !== feature); if (e.target.checked) panel.inherited_features.push(feature); remember(); } }))));
      list.append(h('article', { class: 'layout-card stack' }, h('div', { class: 'section-heading' }, h('strong', {}, `${index + 1} · ${panel.label}`), h('div', { class: 'actions' }, up, down)),
        editInput(`項目 ${index + 1} の名前`, panel.label, value => { panel.label = value; }),
        editInput(`項目 ${index + 1} の区分`, panel.section, value => { panel.section = value; }),
        h('p', { class: 'muted small' }, panel.description_ja), panel.reference ? picture(panel.reference.path, `${panel.label}の参照画像`) : null, details,
        button('この項目を外す', () => { proposal.panels.splice(index, 1); remember(); paint(); }, 'quiet')));
    });
    showStatus();
  };
  const saveOriginal = async () => {
    if (input.value === original) return;
    if (conflict) throw new Error('最新の構成を読み込んでから注文してください。');
    await flushCaptions('character', name);
    job = await API.saveComment({ name, kind: 'character', stage: 'layout', comment: input.value, layout_panels: layoutValues(proposal.panels), layout_expected: saved });
    original = job.original_comment; remember();
  };
  const propose = async () => {
    if (busy) return;
    if (conflict) throw new Error('最新の構成を読み込んでから注文してください。');
    busy = true; controls.disabled = true; showStatus();
    try {
      await flushCaptions('character', name);
      job = await API.saveComment({ name, kind: 'character', stage: 'layout', comment: input.value, layout_panels: layoutValues(proposal.panels), layout_expected: saved });
      original = job.original_comment; remember();
      job = await API.interpretComment(job.job_id);
      proposal = structuredClone(job.proposal); remember();
    } catch (error) {
      if (job) job = await API.job(job.job_id);
      throw error;
    } finally { busy = false; controls.disabled = false; paint(); }
  };
  const confirm = async () => {
    if (conflict || busy || input.value !== original || job && !['awaiting_confirmation', 'confirmed'].includes(job.status)) throw new Error('注文を解釈して、構成案を確認してください。');
    controls.disabled = true;
    try {
      if (job?.status === 'awaiting_confirmation') job = await API.confirmLayout(job.job_id, proposal);
      else await API.saveLayout(name, saved, layoutValues(proposal.panels));
      saved = await API.sheetLayout(name); clearDraft(storageKey); paint();
    } finally { controls.disabled = false; }
  };
  controls.append(field('シート構成への注文', input, '載せる項目の希望はこちらへ。衣装の種類や項目数は自由に指定できます。'),
    h('div', { class: 'actions' }, button('原文を保存', e => action(e.currentTarget, saveOriginal), 'quiet'), button('言葉から構成案を作る', e => action(e.currentTarget, propose))), explanation, list,
    button('項目を追加', () => {
      proposal.panels.push({ key: `custom_${crypto.randomUUID().replaceAll('-', '')}`, label: '新しい項目', section: '追加項目', kind: 'full', parts: [{ feature: 'subject', description_en: '', avoid_en: '' }], role_features: [], inherited_features: Object.keys(features), seed_offset: Math.max(-1, ...saved.map(p => p.seed_offset), ...proposal.panels.map(p => p.seed_offset)) + 1, description_ja: '描く内容を注文へ書いて構成案を作るか、詳細欄に英語で指定してください。', reference: null }); remember(); paint();
    }, 'quiet'), button('この構成を確定', e => action(e.currentTarget, confirm)), button('下書きを保存済み構成に戻す', e => action(e.currentTarget, async () => {
      if (job && job.status !== 'confirmed') { await API.discardLayout(job.job_id); job = null; original = ''; }
      saved = await API.sheetLayout(name); conflict = false;
      input.value = original;
      proposal = { summary_ja: '', questions: [], panels: describe(saved) };
      clearDraft(storageKey); remember(); paint();
    }), 'quiet'));
  target.append(h('section', { class: 'layout-editor stack' }, h('h3', {}, 'シートに載せる項目'), h('p', { class: 'muted' }, '順番と内容を選び、構成を確定してから描きます。過去のシートは変わりません。'), status, controls));
  paint();
  return { save: saveOriginal, requireConfirmed: () => {
    if (conflict || busy || input.value !== original || changed() || job && job.status !== 'confirmed') throw new Error('シート構成を確定してから生成してください。');
  } };
}

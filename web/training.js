import { h, picture, dateText } from './ui.js?v=studio-3';

export function trainingSelection(samples, references) {
  if (!samples) return null;
  const labels = {primary:'優先して学習',normal:'通常の教材',reference:'参考のみ・教材には含めない'};
  return h('section', {class:'stack'}, h('h3', {}, '学習での画像の使い方'),
    samples.map(item => h('div', {class:'small'}, h('strong', {}, `画像 ${references.findIndex(r => r.sample_index === item.reference.sample_index && r.path === item.reference.path) + 1} · ${labels[item.priority]}`), h('p', {class:'muted'}, item.reason_ja))),
    h('details', {}, h('summary', {}, '学習への反映方法'), h('p', {class:'muted small'}, '優先画像は通常の2倍の頻度で使います。画像全体の学習なので、顔・衣装・画風を完全に分離するものではありません。')));
}

export function trainingMaterials(job, title = '今回学習する教材') {
  if (!job?.materials) return h('p', { class: 'muted' }, 'このLoRAの学習教材の写しは記録されていません。現在の参考画像を過去の教材とは扱いません。');
  return h('section', { class: 'stack' }, h('h3', {}, title), h('p', { class: 'muted' }, `${job.materials.length} 枚・${job.steps} ステップ · ${dateText(job.created_at)}`),
    job.training_selection ? trainingSelection(job.training_selection.samples, job.training_selection.references) : null,
    h('div', { class: 'sample-grid training-grid' }, job.materials.map((item, index) => h('article', { class: 'sample-card' },
      picture(item.path, `学習教材 ${index + 1}`), h('div', { class: 'sample-content stack' }, h('strong', {}, `教材 ${index + 1}`), h('p', {}, item.appearance_ja),
      h('p', { class: 'muted small' }, '実際に学習へ渡す説明'), h('pre', { class: 'training-caption' }, item.caption),
      h('details', {}, h('summary', {}, '元のコメント（教材へ転記しません）'), h('p', {}, item.original_comment || 'コメントなし')))))));
}

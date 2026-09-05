import { h, picture, dateText } from './ui.js?v=studio-2';

export function trainingMaterials(job, title = '今回学習する教材') {
  if (!job?.materials) return h('p', { class: 'muted' }, 'このLoRAの学習教材の写しは記録されていません。現在の参考画像を過去の教材とは扱いません。');
  return h('section', { class: 'stack' }, h('h3', {}, title), h('p', { class: 'muted' }, `${job.materials.length} 枚・${job.steps} ステップ · ${dateText(job.created_at)}`),
    h('div', { class: 'sample-grid training-grid' }, job.materials.map((item, index) => h('article', { class: 'sample-card' },
      picture(item.path, `学習教材 ${index + 1}`), h('div', { class: 'sample-content stack' }, h('strong', {}, `教材 ${index + 1}`), h('p', {}, item.appearance_ja),
      h('p', { class: 'muted small' }, '実際に学習へ渡す説明'), h('pre', { class: 'training-caption' }, item.caption),
      h('details', {}, h('summary', {}, '元のコメント（教材へ転記しません）'), h('p', {}, item.original_comment || 'コメントなし')))))));
}

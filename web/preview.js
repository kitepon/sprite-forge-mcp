import { API } from './api.js';
import { h, field, button, picture, action, notice, dateText } from './ui.js';
import { jobs, subscribe, refreshJobs, runJob, jobView, terminal } from './jobs.js';
import { draft, saveDraft } from './drafts.js';

const labels = { ok: 'OK：残したい画像', ng: 'NG：直したい画像', '': '未判定' };
export const reviewLabel = rating => rating === 'ng' ? 'この画像のどこがNGでしたか？' : rating === 'ok' ? 'この画像で残したいところは？（任意）' : 'OK・NGを選んでから理由を書けます';
export const focusLabel = rating => rating === 'ng' ? '直したい場所（押した場所をOKの絵に寄せて学習します）' : rating === 'ok' ? '残したい場所の記録（寄せる場所はNGで選びます）' : 'OK・NGを選んでから場所を選べます';
export const meaningSummary = (rating, meaning) => {
  if (!meaning) return '';
  if (rating === 'ok') return `維持：${meaning.preserve.join('、') || '指定なし'}`;
  return `修正：${meaning.fix.join('、') || '指定なし'}／維持：${meaning.preserve.join('、') || '指定なし'}`;
};

export function previewReviewCard(name, jobId, image, index, changed) {
  let review = image.review, rating = review.rating, focus = [...review.focus];
  let pending = 0, failed = null, timer, chain = Promise.resolve(), queued = '', meaningSignature = '';
  const comment = h('textarea', { rows: 3 }, review.comment);
  const caption = h('span', { class: 'field-label' });
  const help = h('small', { class: 'muted' });
  const place = h('p', { class: 'small muted' });
  const status = h('p', { class: 'small muted', role: 'status' });
  const meaning = h('div', { class: 'review-meaning stack' });
  const history = h('details', { class: 'review-history' });
  const controls = ['ok', 'ng', ''].map(value => button(labels[value], () => { rating = value; display(); persist(); changed(); }, 'quiet'));
  const focuses = [['hair', '髪'], ['face', '顔'], ['outfit', '衣装'], ['body', '体形'], ['style', '画風']].map(([key, label]) =>
    button(label, () => { focus = focus.includes(key) ? focus.filter(v => v !== key) : [...focus, key]; display(); persist(); }, 'quiet'));
  const value = () => ({ rating, comment: comment.value, focus: [...focus] });
  let saved = JSON.stringify(value());
  function display() {
    caption.textContent = reviewLabel(rating);
    place.textContent = focusLabel(rating);
    comment.disabled = !rating;
    comment.placeholder = rating === 'ng' ? '例：髪型がサンプルと違う。ツインテールがなくなっている' : '例：顔立ちと衣装はこのまま残したい';
    help.textContent = rating === 'ng' ? '直してほしい箇所を書いてください（任意）' : '理由は任意です。OK・NGだけでも再学習できます。';
    controls.forEach((node, i) => node.setAttribute('aria-pressed', String(['ok', 'ng', ''][i] === rating)));
    focuses.forEach((node, i) => { node.disabled = !rating; node.setAttribute('aria-pressed', String(focus.includes(['hair', 'face', 'outfit', 'body', 'style'][i]))); });
    displayMeaning();
  }
  function displayMeaning() {
    const signature = JSON.stringify([rating, review.meaning, review.meaning_source, review.revision]);
    if (signature === meaningSignature) return;
    meaningSignature = signature;
    meaning.replaceChildren();
    history.hidden = !review.history?.length;
    history.replaceChildren(h('summary', {}, '判定とコメントの履歴'), ...(review.history || []).map((item, i) =>
      h('div', { class: 'stack small' }, h('strong', {}, `以前の判定 ${i + 1}：${labels[item.rating]}`), h('p', {}, item.comment || '理由なし'),
        item.meaning ? h('p', {}, meaningSummary(item.rating, item.meaning)) : null)));
    if (!review.meaning) return;
    const current = review.meaning, revision = review.revision, ok = rating === 'ok';
    const preserve = h('textarea', { rows: 2 }, current.preserve.join('\n'));
    const fix = ok ? null : h('textarea', { rows: 2 }, current.fix.join('\n'));
    const generation = ok ? null : h('textarea', { rows: 2 }, current.description_en || '');
    const lines = control => control.value.split('\n').map(v => v.trim()).filter(Boolean);
    meaning.append(...[h('strong', {}, review.meaning_source === 'user' ? '訂正した内容' : 'AIが読み取った内容'),
      ok ? null : h('p', {}, `直したい箇所：${current.fix.join('、') || '指定なし'}`),
      h('p', {}, `残したい箇所：${current.preserve.join('、') || '指定なし'}`),
      ok || !current.description_en ? null : h('details', {}, h('summary', {}, '生成文の詳細'),
        h('pre', { class: 'training-caption' }, current.description_en)),
      ...current.questions.map(q => h('p', { class: 'review-question' }, q)),
      current.questions.length ? h('p', { class: 'small' }, '上の理由に回答を追記するか、下で解釈を訂正してください。') : null,
      h('details', {}, h('summary', {}, '読み取った内容を訂正する'),
        ok ? null : field('直したい箇所', fix), field('残したい箇所', preserve),
        ok ? null : field('生成文（英語）', generation),
        button('この内容に訂正する', e => action(e.currentTarget, async () => {
          await flush();
          review = await API.correctPreviewInterpretation(name, jobId, image.id, {
            revision, meaning: { fix: ok ? [] : lines(fix), preserve: lines(preserve), questions: [], description_en: ok ? '' : generation.value.trim() },
          });
          status.textContent = '訂正を保存しました'; displayMeaning(); changed();
        }), 'quiet'))].filter(Boolean));
  }
  function persist() {
    clearTimeout(timer); timer = null;
    const payload = value(), text = JSON.stringify(payload);
    if (text === saved && !failed && !pending || text === queued && pending) return chain;
    queued = text; pending++; status.textContent = '保存中…';
    chain = chain.then(async () => {
      try {
        review = await API.savePreviewReview(name, jobId, image.id, { ...payload, revision: review.revision });
        saved = text; failed = null;
        status.textContent = '保存済み'; displayMeaning();
      } catch (error) {
        failed = error;
        status.textContent = `判定を保存できませんでした：${error.message}`;
      } finally { pending--; changed(); }
    });
    return chain;
  }
  async function flush() { await persist(); if (failed) throw failed; }
  comment.addEventListener('input', () => { clearTimeout(timer); status.textContent = '未保存'; timer = setTimeout(persist, 400); });
  const reload = button('最新の判定を確認する', e => action(e.currentTarget, async () => {
    const latest = (await API.previewReviews(name, jobId)).pictures.find(p => p.id === image.id).review;
    review = latest;
    status.textContent = `現在の保存内容は「${labels[latest.rating]}：${latest.comment || '理由なし'}」です。入力中の内容で保存する場合は「保存をやり直す」を押してください。`;
  }), 'text-link');
  const node = h('article', { class: 'preview-review-card stack' }, h('h3', {}, `生成画像 ${index + 1}`),
    picture(image.path, `生成画像 ${index + 1}`), h('div', { class: 'review-rating actions', 'aria-label': 'この画像の判定' }, controls),
    h('label', { class: 'field' }, caption, comment, help),
    h('div', {}, place, h('div', { class: 'actions review-focus' }, focuses)),
    status, h('details', {}, h('summary', {}, '保存できなかったとき'), reload, button('保存をやり直す', () => persist(), 'text-link')), meaning, history);
  status.textContent = review.revision ? '保存済み' : '未判定';
  display(); displayMeaning();
  return { node, flush, rating: () => rating, dispose: () => clearTimeout(timer), update(next) {
    if (next.revision < review.revision || pending || JSON.stringify(value()) !== saved || failed) return;
    review = next; rating = next.rating; focus = [...next.focus]; comment.value = next.comment;
    saved = JSON.stringify(value()); display(); displayMeaning();
  } };
}

export async function previewGallery(target, name, style, cleanup, setReady, next) {
  const key = `preview-gallery:${name}:${style}`;
  let selected = draft(key, ''), disposed = false, loading = false, baseline = null, adopted = null, source = null;
  let optionsSignature = '', comparisonSignature = '';
  const cards = new Map();
  const select = h('select', { 'aria-label': '確認する学習結果' });
  const counts = h('p', { class: 'review-counts', role: 'status' });
  const reason = h('p', { class: 'small muted', role: 'status' });
  const grid = h('div', { class: 'preview-review-grid' });
  const progress = h('div'), comparison = h('div'), error = h('p', { class: 'error-text', role: 'alert' });
  const start = button('この判定でLoRAを再学習する', e => action(e.currentTarget, async () => {
    await flush();
    const prior = jobs.find(j => j.kind === 'preview_learning' && j.source_job_id === selected && (j.status === 'awaiting_answers' || !terminal(j)));
    const requestId = prior?.job_id || crypto.randomUUID();
    const result = await runJob({ kind: 'preview_learning', name, source_job_id: selected }, '判定から再学習',
      () => API.relearnPreview(name, selected, requestId), prior || null);
    if (result?.preview_job_id) pick(result.preview_job_id);
    await refresh();
  }));
  const adopt = button('この学習結果を使って一枚シートへ', e => action(e.currentTarget, async () => {
    await flush(); const record = await API.adoptPreview(name, selected);
    adopted = record.adopted_preview_job_id; setReady(true, ''); await next();
  }));
  function summarize() {
    const ratings = [...cards.values()].map(card => card.rating());
    const ok = ratings.filter(v => v === 'ok').length, ng = ratings.filter(v => v === 'ng').length;
    counts.textContent = `OK ${ok}枚 ・ NG ${ng}枚 ・ 未判定 ${ratings.length - ok - ng}枚`;
    const running = jobs.some(j => j.kind === 'preview_learning' && j.source_job_id === selected && !terminal(j));
    start.disabled = !ok || !ng || !!source?.relearning_unavailable_reason || running;
    reason.textContent = source?.relearning_unavailable_reason || (running ? 'この判定の再学習を実行中です。' : !ng && ok ? 'すべてOKなら、そのまま一枚シートへ進めます。' : !ok && ng ? 'OKがありません。追加生成、注文の修正、参考画像の見直しができます。' : !ok || !ng ? '再学習にはOKとNGをそれぞれ1枚以上選んでください。未判定は使いません。' : 'NGで選んだ場所をOKの絵に寄せてLoRAを直します。読み取った生成文で新しいプレビューを作ります。理由の不明点がある場合だけ質問します。');
    adopt.disabled = !selected || jobs.find(j => j.job_id === selected)?.status !== 'completed' || running;
    setReady(selected === adopted, selected === adopted ? '' : '画像を確認し、「この学習結果を使って一枚シートへ」を押してください。');
  }
  function pick(id) {
    if (selected === id) return;
    cards.forEach(card => card.dispose()); cards.clear(); grid.replaceChildren();
    selected = id; saveDraft(key, id); source = null;
  }
  async function flush() { await Promise.all([...cards.values()].map(card => card.flush())); }
  select.addEventListener('change', async () => {
    try { await flush(); pick(select.value); await refresh(); } catch (e) { error.textContent = e.message; select.value = selected; }
  });
  async function refresh() {
    if (loading || disposed) return;
    loading = true;
    try {
      const previews = jobs.filter(j => j.kind === 'preview' && j.name === name && (!style || (j.style || '') === style));
      const newest = baseline && previews.find(j => !baseline.has(j.job_id));
      if (newest) { await flush(); pick(newest.job_id); baseline = null; }
      if (!previews.some(j => j.job_id === selected)) pick(previews[0]?.job_id || '');
      const options = JSON.stringify(previews.map(j => [j.job_id, j.pictures?.length]));
      if (options !== optionsSignature) {
        optionsSignature = options;
        select.replaceChildren(...previews.map(j => h('option', { value: j.job_id }, `${j.learning_job_id ? '再学習後' : 'プレビュー'} · ${dateText(j.created_at)} · ${j.pictures?.length || 0}枚`)));
      }
      select.value = selected;
      if (!selected) { summarize(); return; }
      const current = jobs.find(j => j.job_id === selected);
      const learning = jobs.find(j => j.job_id === current.learning_job_id) || jobs.find(j => j.kind === 'preview_learning' && j.source_job_id === selected);
      if (learning?.status === 'previewing' && learning.preview_job_id !== selected) {
        await flush(); pick(learning.preview_job_id); loading = false; return refresh();
      }
      const id = selected;
      const view = await API.previewReviews(name, id);
      if (disposed || id !== selected) return;
      source = view; error.textContent = '';
      for (const [index, image] of view.pictures.entries()) {
        if (cards.has(image.id)) cards.get(image.id).update(image.review);
        else { const card = previewReviewCard(name, id, image, index, summarize); cards.set(image.id, card); grid.append(card.node); }
      }
      progress.replaceChildren(jobView(learning?.status === 'previewing' ? current : learning || current, { hideImages: true, title: learning ? '判定から再学習' : 'プレビュー' }));
      const compareKey = `${selected}:${learning?.job_id || ''}`;
      if (compareKey !== comparisonSignature) comparison.replaceChildren();
      if (compareKey !== comparisonSignature && current.learning_job_id && learning) {
        const old = jobs.find(j => j.job_id === learning.source_job_id);
        comparison.append(h('details', { class: 'preview-comparison' }, h('summary', {}, '再学習前の画像と判定を見る'),
          h('div', { class: 'preview-review-grid' }, (learning.reviews || []).map(p => h('figure', {}, picture(p.path, '再学習前'),
            h('figcaption', {}, `${labels[p.review.rating]}：${p.review.comment || '理由なし'}`),
            p.review.meaning ? h('p', {}, meaningSummary(p.review.rating, p.review.meaning)) : null))),
          old ? button('以前の学習結果を使う', async () => { await flush(); pick(old.job_id); await refresh(); }, 'quiet') : null));
      }
      comparisonSignature = compareKey;
      summarize();
    } catch (e) { if (!disposed) error.textContent = `判定を読み込めませんでした：${e.message}`; }
    finally { loading = false; }
  }
  target.append(h('section', { class: 'stack preview-review' }, field('確認する学習結果', select), comparison, counts,
    h('p', { class: 'muted' }, '各画像にOK・NGを付けてください。画像を押すと拡大できます。判定は自動保存します。'), grid,
    h('div', { class: 'stack' }, progress, reason, h('div', { class: 'actions' }, start, adopt)), error));
  setReady(false, 'プレビューを読み込んでいます。');
  adopted = (await API.character(name)).adopted_preview_job_id;
  cleanup.push(() => { disposed = true; cards.forEach(card => card.dispose()); });
  cleanup.push(subscribe(refresh));
  await refreshJobs(); await refresh();
  return { flush, select: async id => { await flush(); pick(id); await refresh(); }, followNext() { baseline = new Set(jobs.map(j => j.job_id)); } };
}

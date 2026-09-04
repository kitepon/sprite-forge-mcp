import { API } from './api.js?v=studio-2';

export const $ = (selector, root = document) => root.querySelector(selector);
export function element(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (name.startsWith('on')) node.addEventListener(name.slice(2), value);
    else if (name === 'class') node.className = value;
    else node.setAttribute(name, value === true ? '' : String(value));
  }
  node.append(...children.flat(Infinity).filter(child => child != null && child !== false).map(child => child instanceof Node ? child : document.createTextNode(String(child))));
  return node;
}
export const h = element;
const paths = {
  spark: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',
  home: 'm3 10 9-7 9 7M5 9v12h14V9M9 21v-8h6v8',
  grid: 'M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3ZM14 14h7v7h-7Z',
  activity: 'M3 12h4l3-8 4 16 3-8h4',
  tool: 'm14 5 5 5M4 20l4-1L21 6l-3-3L5 16Z',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  plus: 'M12 5v14M5 12h14',
  check: 'm5 12 4 4L19 6',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5',
  image: 'M3 3h18v18H3Zm0 14 6-6 5 5 3-3 4 4M16 7h.01',
  close: 'm6 6 12 12M6 18 18 6',
  download: 'M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4',
  expand: 'M8 3H3v5m13-5h5v5M3 16v5h5m8 0h5v-5',
  palette: 'M12 3a9 9 0 1 0 0 18c4 0 0-5 3-5h3c5 0 4-13-6-13ZM7 9h.01M11 6h.01M16 8h.01M6 14h.01',
  layers: 'm12 3 10 6-10 6L2 9Zm-9 11 9 5 9-5M3 18l9 5 9-5',
};
export function icon(name, size = 20) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  for (const [key, value] of Object.entries({ viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': true })) node.setAttribute(key, value);
  const path = document.createElementNS(node.namespaceURI, 'path'); path.setAttribute('d', paths[name] || paths.spark); node.append(path); return node;
}
export const card = (title, body, footer = null) => h('section', { class: 'card stack' }, title ? h('h2', {}, title) : null, body, footer);
export const field = (label, control, help = '') => h('label', { class: 'field' }, h('span', { class: 'field-label' }, label), control, help ? h('small', { class: 'muted' }, help) : null);
export const button = (text, action, className = '') => h('button', { type: 'button', class: className, onclick: action }, text);
export const link = (text, href, className = 'button-link') => h('a', { href, class: className }, text);
export function empty(title, description, action) { return h('div', { class: 'empty' }, icon('image', 32), h('h3', {}, title), h('p', {}, description), action); }
export function notice(message, isError = false) {
  const root = $('#notice');
  const item = h('div', { class: `toast ${isError ? 'error' : ''}`, role: isError ? 'alert' : 'status' }, icon(isError ? 'activity' : 'check'), h('span', {}, message), button(icon('close'), () => item.remove(), 'icon-button'));
  item.lastChild.setAttribute('aria-label', '通知を閉じる'); root.append(item);
  if (!isError) setTimeout(() => item.remove(), 6000);
}
export async function action(control, work) {
  if (control.disabled) return;
  control.disabled = true; control.setAttribute('aria-busy', 'true');
  try { return await work(); } catch (error) { notice(error.message, true); }
  finally { control.disabled = false; control.removeAttribute('aria-busy'); }
}
export function confirmAction(message) {
  return new Promise(resolve => {
    const dialog = h('dialog', { class: 'confirm-dialog', 'aria-label': '参考画像を外す' }, h('h3', {}, message), h('p', { class: 'muted small' }, '参考画像と説明を台帳から外します。元のアップロード画像は残ります。'));
    let accepted = false;
    dialog.append(h('div', { class: 'actions' }, button('戻る', () => dialog.close(), 'quiet'), button('参考画像から外す', () => { accepted = true; dialog.close(); })));
    dialog.addEventListener('close', () => { dialog.remove(); resolve(accepted); }); document.body.append(dialog); dialog.showModal();
  });
}
export function picture(path, label = '画像', options = {}) {
  if (!path) return h('div', { class: 'image-placeholder' }, icon('image', 36));
  const src = API.file(path) + (options.version ? `&v=${encodeURIComponent(options.version)}` : '');
  const img = h('img', { src, alt: label, loading: 'lazy', decoding: 'async', onerror: () => { img.replaceWith(h('span', { class: 'image-unavailable' }, '画像を読み込めません')); } });
  if (options.plain) return img;
  return h('button', { type: 'button', class: `picture ${options.class || ''}`, 'aria-label': `${label}を拡大`, onclick: () => lightbox([{ path, label, src }]) }, img, h('span', { class: 'expand-icon' }, icon('expand', 16)));
}
export function lightbox(images, index = 0) {
  const previousFocus = document.activeElement;
  const dialog = h('dialog', { class: 'lightbox', 'aria-label': '画像ビューアー' });
  const stage = h('div', { class: 'lightbox-stage' }); const caption = h('span');
  const download = link([icon('download'), 'ダウンロード'], '#', 'button-link quiet'); download.setAttribute('download', '');
  const show = () => { const current = images[index]; stage.replaceChildren(h('img', { src: current.src || API.file(current.path), alt: current.label || '生成画像' })); caption.textContent = `${current.label || '生成画像'}${images.length > 1 ? ` · ${index + 1} / ${images.length}` : ''}`; download.href = current.src || API.file(current.path); };
  const close = button(icon('close'), () => dialog.close(), 'icon-button'); close.setAttribute('aria-label', '画像を閉じる');
  dialog.append(h('header', { class: 'lightbox-head' }, caption, download, close), stage,
    images.length > 1 ? h('div', { class: 'actions centered' }, button('← 前の画像', () => { index = (index - 1 + images.length) % images.length; show(); }, 'quiet'), button('次の画像 →', () => { index = (index + 1) % images.length; show(); }, 'quiet')) : null);
  dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => { dialog.remove(); previousFocus?.focus(); });
  document.body.append(dialog); show(); dialog.showModal();
}
export function errorState(root, error) { root.replaceChildren(empty('読み込めませんでした', error.message, button('もう一度読み込む', () => window.dispatchEvent(new HashChangeEvent('hashchange')), 'quiet'))); }
export function pageHead(eyebrow, title, description, extra) { return h('header', { class: 'page-head' }, h('div', {}, h('p', { class: 'eyebrow' }, eyebrow), h('h1', {}, title), description ? h('p', { class: 'muted' }, description) : null), extra); }
export function dateText(value) { return value ? new Intl.DateTimeFormat('ja-JP', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : '日時の記録なし'; }

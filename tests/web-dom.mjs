// web/ui.js の h()/element() と web/*.js が実際に呼ぶDOM APIだけを模倣する共有スタブ。
// 推測で機能を足さず、既存の各試験ファイルが個別に持っていたFakeNode/documentの共通部分だけをここへ寄せる。
export class Node {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.attrs = {};
    this.value = '';
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  setAttribute(key, value) { this.attrs[key] = value; if (key === 'value') this.value = value; }
  removeAttribute(key) { delete this.attrs[key]; }
  addEventListener(name, fn) { (this.events ||= {})[name] = fn; }
  append(...items) {
    this.children.push(...items);
    if (this.tag === 'textarea') this.value = this.children.join('');
  }
  replaceChildren(...items) {
    this.children = [];
    this.append(...items);
  }
  insertBefore(item, before) { this.children.splice(this.children.indexOf(before), 0, item); }
  querySelectorAll(tag) { return all(this).filter(node => node !== this && node.tag === tag); }
  get lastChild() { return this.children.at(-1); }
  remove() {}
  reportValidity() { return true; }
}

export function installDom() {
  globalThis.Node = Node;
  globalThis.localStorage = { getItem: () => null, setItem() {} };
  globalThis.document = {
    createElement: tag => new Node(tag),
    createElementNS: (_namespace, tag) => new Node(tag),
    createTextNode: text => text,
    querySelector: () => new Node('notice'),
    addEventListener() {},
    removeEventListener() {},
  };
}

export const all = node => [node, ...node.children.filter(child => child instanceof Node).flatMap(all)];

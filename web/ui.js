export const $ = (selector, root = document) => root.querySelector(selector);

export function element(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else if (name === "class") node.className = value;
    else node.setAttribute(name, value);
  }
  node.append(...children.flat().filter(Boolean).map((child) =>
    child instanceof Node ? child : document.createTextNode(String(child))));
  return node;
}

export function card(title, body, footer = null) {
  return element("section", { class: "card" }, element("h2", {}, title), body, footer && element("footer", {}, footer));
}

export function notice(message, isError = false) {
  const target = $("#notice");
  target.textContent = message;
  target.className = isError ? "error" : "";
}

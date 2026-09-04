const key = 'sprite-forge.drafts.v1';
const values = JSON.parse(localStorage.getItem(key) || '{}');
export const draft = (name, fallback = '') => Object.hasOwn(values, name) ? values[name] : fallback;
export function saveDraft(name, value) { values[name] = value; localStorage.setItem(key, JSON.stringify(values)); }
export function clearDraft(name) { delete values[name]; localStorage.setItem(key, JSON.stringify(values)); }
// File objects stay in this tab when moving between steps; they are never called uploaded.
export const pendingFiles = new Map();

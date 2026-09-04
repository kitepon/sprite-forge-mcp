export async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  return body;
}

export const API = {
  gpu: () => api("/api/gpu"),
  sprite: (prompt, seed) => api(`/api/generate?${new URLSearchParams({ prompt, seed, count: 1 })}`, { method: "POST" }),
  characters: () => api("/api/characters"),
  character: (name) => api(`/api/characters/${encodeURIComponent(name)}`),
  createCharacter: (name, char_desc, attr = "", trigger = "", lora_name = "") => api(`/api/characters?${new URLSearchParams({ name, char_desc, attr, trigger, lora_name })}`, { method: "POST" }),
  addSamples: (name, images, captions = "") => api(`/api/characters/${encodeURIComponent(name)}/samples?${new URLSearchParams({ images, captions })}`, { method: "POST" }),
  removeSample: (name, index) => api(`/api/characters/${encodeURIComponent(name)}/samples/${index}`, { method: "DELETE" }),
  setCaption: (name, index, caption) => api(`/api/characters/${encodeURIComponent(name)}/samples/${index}/caption?${new URLSearchParams({ caption })}`, { method: "POST" }),
  train: (name, steps = 1200) => api(`/api/lora?${new URLSearchParams({ name, steps })}`, { method: "POST" }),
  previewCharacter: (name, tags, seed = 1, count = 1) => api(`/api/characters/${encodeURIComponent(name)}/preview?${new URLSearchParams({ tags, seed, count })}`, { method: "POST" }),
  bible: (name, seed = 1, style = "") => api(`/api/bible?${new URLSearchParams({ name, seed, style })}`, { method: "POST" }),
  panels: () => api("/api/panels"),
  redraw: (name, panel, tags = "", seed = 1, avoid = "") => api(`/api/panel?${new URLSearchParams({ name, panel, tags, seed, avoid })}`, { method: "POST" }),
  fromBible: (name, prompt, seed = 1, style = "") => api(`/api/from-bible?${new URLSearchParams({ name, prompt, seed, style })}`, { method: "POST" }),
  image: (prompt, style, seed = 1) => api(`/api/image?${new URLSearchParams({ prompt, style, seed })}`, { method: "POST" }),
  styles: () => api("/api/styles"),
  createStyle: (name, note = "") => api(`/api/styles?${new URLSearchParams({ name, note })}`, { method: "POST" }),
  addStyleSamples: (name, images, captions = "") => api(`/api/styles/${encodeURIComponent(name)}/samples?${new URLSearchParams({ images, captions })}`, { method: "POST" }),
  trainStyle: (name, steps = 1200) => api(`/api/styles/${encodeURIComponent(name)}/train?${new URLSearchParams({ steps })}`, { method: "POST" }),
  deleteStyle: (name) => api(`/api/styles/${encodeURIComponent(name)}`, { method: "DELETE" }),
  setCharacterStyle: (name, style, strength = 0.7) => api(`/api/characters/${encodeURIComponent(name)}/style?${new URLSearchParams({ style, strength })}`, { method: "POST" }),
  upload: async (files) => { const body = new FormData(); [...files].forEach((file) => body.append("files", file)); return api("/api/upload", { method: "POST", body }); },
  file: (path) => `/api/file?${new URLSearchParams({ path })}`,
  loras: () => api("/api/loras"),
  transparent: (image_id) => api(`/api/transparent?${new URLSearchParams({ image_id })}`, { method: "POST" }),
  pixelize: (image_id) => api(`/api/pixelize?${new URLSearchParams({ image_id, block: 8, posterize: 4 })}`, { method: "POST" }),
  jobs: () => api("/api/jobs"),
  job: (jobId) => api(`/api/jobs/${encodeURIComponent(jobId)}`),
  events: (since = "") => new EventSource(`/api/events?${new URLSearchParams({ since })}`),
};

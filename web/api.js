export async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  return body;
}

export const API = {
  gpu: () => api("/api/gpu"),
  sprite: (prompt, seed) => api(`/api/generate?${new URLSearchParams({ prompt, seed, count: 1 })}`, { method: "POST" }),
  bible: (source, name, char_desc, attr, style_refs = "", style_preset = "") => api(`/api/bible?${new URLSearchParams({ source, name, char_desc, attr, style_refs, style_preset })}`, { method: "POST" }),
  fromBible: (name, prompt, style_preset = "", style_refs = "", seed = 1) => api(`/api/from-bible?${new URLSearchParams({ name, prompt, style_preset, style_refs, seed })}`, { method: "POST" }),
  image: (prompt, style_preset = "", style_refs = "", seed = 1) => api(`/api/image?${new URLSearchParams({ prompt, style_preset, style_refs, seed })}`, { method: "POST" }),
  presets: () => api("/api/presets"),
  savePreset: (name, images, note = "") => api(`/api/presets?${new URLSearchParams({ name, images, note })}`, { method: "POST" }),
  deletePreset: (name) => api(`/api/presets/${encodeURIComponent(name)}`, { method: "DELETE" }),
  upload: async (files) => { const body = new FormData(); [...files].forEach((file) => body.append("files", file)); return api("/api/upload", { method: "POST", body }); },
  file: (path) => `/api/file?${new URLSearchParams({ path })}`,
  loras: () => api("/api/loras"),
  train: (bible_name) => api(`/api/lora?${new URLSearchParams({ bible_name })}`, { method: "POST" }),
  transparent: (image_id) => api(`/api/transparent?${new URLSearchParams({ image_id })}`, { method: "POST" }),
  pixelize: (image_id) => api(`/api/pixelize?${new URLSearchParams({ image_id, block: 8, posterize: 4 })}`, { method: "POST" }),
  jobs: () => api("/api/jobs"),
  job: (jobId) => api(`/api/jobs/${encodeURIComponent(jobId)}`),
  events: (since = "") => new EventSource(`/api/events?${new URLSearchParams({ since })}`),
};

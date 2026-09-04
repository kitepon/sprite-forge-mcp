export async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  return body;
}

export const API = {
  gpu: () => api("/api/gpu"),
  sprite: (prompt, seed) => api(`/api/generate?${new URLSearchParams({ prompt, seed, count: 1 })}`, { method: "POST" }),
  bible: (source, name, char_desc, attr) => api(`/api/bible?${new URLSearchParams({ source, name, char_desc, attr })}`, { method: "POST" }),
  loras: () => api("/api/loras"),
  train: (bible_name) => api(`/api/lora?${new URLSearchParams({ bible_name })}`, { method: "POST" }),
  transparent: (image_id) => api(`/api/transparent?${new URLSearchParams({ image_id })}`, { method: "POST" }),
  pixelize: (image_id) => api(`/api/pixelize?${new URLSearchParams({ image_id, block: 8, posterize: 4 })}`, { method: "POST" }),
  jobs: () => api("/api/jobs"),
  job: (jobId) => api(`/api/jobs/${encodeURIComponent(jobId)}`),
  events: (since = "") => new EventSource(`/api/events?${new URLSearchParams({ since })}`),
};

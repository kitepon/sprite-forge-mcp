export async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  return body;
}

export const API = {
  gpu: () => api("/api/gpu"),
  startBase: (prompt, seed) => api(`/api/base?${new URLSearchParams({ prompt, seed })}`, { method: "POST" }),
  job: (jobId) => api(`/api/jobs/${encodeURIComponent(jobId)}`),
  // This UI deliberately never opens a global feed: each stream is one job only.
  events: (jobId) => new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`),
};

const BASE_URL = "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export const api = {
  listCases: () => request("/cases"),
  getCase: (id) => request(`/cases/${id}`),
  createCase: (payload) => request("/cases", { method: "POST", body: JSON.stringify(payload) }),
  submitEvidence: (caseId, payload) =>
    request(`/cases/${caseId}/evidence`, { method: "POST", body: JSON.stringify(payload) }),
  // Async by default: the run answers 202 immediately and the sources land one at a
  // time in the gather log, which is what the polling loop renders.
  gatherEvidence: (caseId) => request(`/cases/${caseId}/gather?async_mode=true`, { method: "POST" }),
  getGatherLog: (caseId) => request(`/cases/${caseId}/gather-log`),
  resolveCase: (caseId) => request(`/cases/${caseId}/resolve`, { method: "POST" }),
};

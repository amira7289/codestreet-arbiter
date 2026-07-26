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
  resolveCase: (caseId) => request(`/cases/${caseId}/resolve`, { method: "POST" }),
};

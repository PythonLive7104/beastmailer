// Thin fetch wrapper around the Django REST API.
const BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

export const TOKEN_KEY = "auth_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

function authHeaders(extra = {}) {
  const token = getToken();
  return token ? { ...extra, Authorization: `Token ${token}` } : extra;
}

async function request(path, { method = "GET", body, params } = {}) {
  let url = `${BASE}${path}`;
  if (params) {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== "" && v !== null)
    ).toString();
    if (qs) url += `?${qs}`;
  }
  const res = await fetch(url, {
    method,
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    // Token missing/expired — drop it and bounce to login.
    setToken(null);
    if (!location.pathname.startsWith("/login") && !location.pathname.startsWith("/signup")) {
      location.assign("/login");
    }
  }
  if (!res.ok) {
    let detail;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    const err = new Error(`${res.status} ${res.statusText}`);
    err.detail = detail;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

// Endpoints return a DRF paginated envelope for list views; unwrap results.
const list = (data) => (data && Array.isArray(data.results) ? data.results : data);

export const api = {
  auth: {
    register: (body) => request("/auth/register/", { method: "POST", body }),
    login: (body) => request("/auth/login/", { method: "POST", body }),
    logout: () => request("/auth/logout/", { method: "POST" }),
    me: () => request("/auth/me/"),
    updateProfile: (body) => request("/auth/profile/", { method: "PATCH", body }),
    completeOnboarding: () => request("/auth/onboarding/complete/", { method: "POST" }),
    deleteAccount: (body) => request("/auth/account/", { method: "DELETE", body }),
  },

  dashboard: () => request("/dashboard/"),
  runEngine: () => request("/engine/run/", { method: "POST" }),

  config: {
    get: () => request("/config/"),
    update: (body) => request("/config/", { method: "PATCH", body }),
  },

  mailboxes: {
    list: () => request("/mailboxes/").then(list),
    create: (body) => request("/mailboxes/", { method: "POST", body }),
    update: (id, body) => request(`/mailboxes/${id}/`, { method: "PATCH", body }),
    remove: (id) => request(`/mailboxes/${id}/`, { method: "DELETE" }),
    test: (id) => request(`/mailboxes/${id}/test/`, { method: "POST" }),
    poll: (id) => request(`/mailboxes/${id}/poll/`, { method: "POST" }),
  },

  rules: {
    list: () => request("/rules/").then(list),
    create: (body) => request("/rules/", { method: "POST", body }),
    update: (id, body) => request(`/rules/${id}/`, { method: "PATCH", body }),
    remove: (id) => request(`/rules/${id}/`, { method: "DELETE" }),
    testMatch: (subject) => request("/rules/test_match/", { method: "POST", body: { subject } }),
  },

  templates: {
    list: () => request("/templates/").then(list),
    create: (body) => request("/templates/", { method: "POST", body }),
    update: (id, body) => request(`/templates/${id}/`, { method: "PATCH", body }),
    remove: (id) => request(`/templates/${id}/`, { method: "DELETE" }),
    preview: (id) => request(`/templates/${id}/preview/`, { method: "POST" }),
  },

  placeholders: {
    list: () => request("/placeholders/").then(list),
    create: (body) => request("/placeholders/", { method: "POST", body }),
    update: (id, body) => request(`/placeholders/${id}/`, { method: "PATCH", body }),
    remove: (id) => request(`/placeholders/${id}/`, { method: "DELETE" }),
  },

  messages: {
    list: (params) => request("/messages/", { params }).then(list),
  },

  links: {
    list: () => request("/links/").then(list),
    create: (body) => request("/links/", { method: "POST", body }),
    update: (id, body) => request(`/links/${id}/`, { method: "PATCH", body }),
    remove: (id) => request(`/links/${id}/`, { method: "DELETE" }),
  },

  attachments: {
    list: () => request("/attachments/").then(list),
    // Uploads use multipart/form-data, so bypass the JSON helper.
    create: (formData) => uploadFile("/attachments/", formData),
    remove: (id) => request(`/attachments/${id}/`, { method: "DELETE" }),
  },

  proxies: {
    list: () => request("/proxies/").then(list),
    create: (body) => request("/proxies/", { method: "POST", body }),
    update: (id, body) => request(`/proxies/${id}/`, { method: "PATCH", body }),
    remove: (id) => request(`/proxies/${id}/`, { method: "DELETE" }),
    test: (id) => request(`/proxies/${id}/test/`, { method: "POST" }),
  },

  telegram: {
    get: () => request("/telegram/"),
    update: (body) => request("/telegram/", { method: "PATCH", body }),
    test: (body) => request("/telegram/test/", { method: "POST", body }),
  },

  security: {
    posture: () => request("/security/posture/"),
    events: (params) => request("/events/", { params }).then(list),
    changePassword: (body) => request("/security/change-password/", { method: "POST", body }),
  },

  workspaces: {
    list: () => request("/workspaces/").then(list),
    create: (body) => request("/workspaces/", { method: "POST", body }),
    remove: (id) => request(`/workspaces/${id}/`, { method: "DELETE" }),
    switch: (id) => request(`/workspaces/${id}/switch/`, { method: "POST" }),
    members: (id) => request(`/workspaces/${id}/members/`),
    invite: (id, body) => request(`/workspaces/${id}/invite/`, { method: "POST", body }),
    setRole: (id, memberId, role) =>
      request(`/workspaces/${id}/members/${memberId}/role/`, { method: "POST", body: { role } }),
    removeMember: (id, memberId) =>
      request(`/workspaces/${id}/members/${memberId}/`, { method: "DELETE" }),
    acceptInvite: (code) => request("/invitations/accept/", { method: "POST", body: { code } }),
  },
};

async function uploadFile(path, formData) {
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers: authHeaders(), body: formData });
  if (!res.ok) {
    const err = new Error(`${res.status} ${res.statusText}`);
    try { err.detail = await res.json(); } catch { err.detail = await res.text(); }
    throw err;
  }
  return res.json();
}

// Base URL of the backend (without the /api suffix) for building media/redirect links.
export const SERVER_ORIGIN = BASE.replace(/\/api\/?$/, "");

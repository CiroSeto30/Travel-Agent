// Calls to the backend. The login cookie travels by itself: pages and API share the same address.

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === "string" ? detail : `Request failed with status ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function request(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data?.detail);
  return data;
}

export const getCurrentUser = () => request("/api/auth/me");
export const login = (email, password) => request("/api/auth/login", { method: "POST", body: { email, password } });
export const register = (user) => request("/api/auth/register", { method: "POST", body: user });
export const logout = () => request("/api/auth/logout", { method: "POST" });
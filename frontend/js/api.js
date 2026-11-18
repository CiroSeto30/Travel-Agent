// Calls to the backend. The login cookie travels by itself: pages and API share the same address.

import { readEvents } from "./sse.js";

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

export const getDestinations = () => request("/api/destinations");
export const getItinerary = (id) => request(`/api/itineraries/${id}`);
// selection: [{ day, activity_id }], the whole selection of the trip; answers with the saved itinerary
export const saveActivities = (id, selection) =>
  request(`/api/itineraries/${id}/activities`, { method: "PUT", body: selection });
export const getBookings = () => request("/api/bookings");
export const createConversation = () => request("/api/conversations", { method: "POST" });

// The agent's answer, as the events of the stream: { event, data } (docs/design.md §10)
export async function* sendMessage(conversationId, content) {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(response.status, data?.detail);
  }
  yield* readEvents(response);
}

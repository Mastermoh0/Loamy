// Settings page data layer. UI components only decide how things look; every
// request the Settings page makes lives here.

import { isRealUserId } from "./activitySyncService";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export function getSession() {
  try {
    return JSON.parse(localStorage.getItem("loamy_session") || "{}");
  } catch {
    return {};
  }
}

// Everything user-specific cached in localStorage; wiped on logout so the next
// account on this browser starts clean.
const USER_STORAGE_KEYS = [
  "loamy_session", "gmail_connected", "gmail_email_data",
  "gmail_access_token", "gmail_refresh_token", "gmail_email",
  "loamy_last_sync_at", "loamy_onboarding", "loamy_post_oauth_redirect",
];

export async function logoutUser(userId) {
  try {
    await fetch(`${API_URL}/clear-gmail-data`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });
  } catch (e) {
    console.error("Clear gmail on logout failed:", e);
  }
  USER_STORAGE_KEYS.forEach((k) => localStorage.removeItem(k));
}

async function getJson(path) {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

// SWR keys are null when there is no real session, which skips the request.
export const keys = {
  facts: (userId) => (isRealUserId(userId) ? ["memory", userId] : null),
  gmail: (userId) => (isRealUserId(userId) ? ["gmail-status", userId] : null),
  whatsapp: (userId) => (isRealUserId(userId) ? ["whatsapp-status", userId] : null),
  banks: (userId) => (isRealUserId(userId) ? ["bank-accounts", userId] : null),
};

export async function fetchFacts([, userId]) {
  const res = await getJson(`/memory/${encodeURIComponent(userId)}`);
  if (res.status !== "success") throw new Error(res.error || "Could not load memory");
  return res.data || [];
}

export async function forgetFact(userId, factId) {
  const res = await fetch(
    `${API_URL}/memory/${encodeURIComponent(userId)}/${encodeURIComponent(factId)}`,
    { method: "DELETE" },
  );
  const body = await res.json().catch(() => ({}));
  if (body.status !== "success") throw new Error(body.error || "Could not forget that");
}

export async function fetchGmailStatus([, userId]) {
  const res = await getJson(`/gmail/status/${encodeURIComponent(userId)}`);
  return res.status === "success" ? res.data : { connected: false };
}

export async function fetchWhatsappStatus([, userId]) {
  const res = await getJson(`/whatsapp-link-status?user_id=${encodeURIComponent(userId)}`);
  return { linked: Boolean(res.linked), phone: res.phone_number || "" };
}

export async function fetchBankCount([, userId]) {
  const res = await getJson(`/api/v1/accounts?user_id=${encodeURIComponent(userId)}`);
  return res.status === "success" ? res.data?.count || 0 : 0;
}

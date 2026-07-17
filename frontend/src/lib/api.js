const base = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export const apiBaseUrl = base;

export const token = () => localStorage.getItem("talentforge_token");

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers);
  const accessToken = token();

  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${base}${path}`, { ...options, headers });
  const body = response.status === 204 ? null : await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : response.statusText || `Request failed (${response.status}).`;
    throw new ApiError(detail, response.status);
  }

  return body;
}

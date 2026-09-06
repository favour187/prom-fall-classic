/**
 * Typed API client for the FastAPI backend.
 * - Always talks to the same origin (`/api`), so it works behind the Vite
 *   dev proxy and in production behind the same host.
 * - Normalises the backend error envelope into a typed `ApiError`.
 * - Attaches the bearer token from localStorage (kept in sync with useAuth).
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const TOKEN_KEY = "auth_token";

export interface ApiErrorBody {
  code: string;
  message: string;
  details?: unknown;
  request_id?: string;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;
  requestId?: string;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.requestId = body.request_id;
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export interface ApiOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string | null;
  signal?: AbortSignal;
  query?: Record<string, string | number | boolean | undefined>;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, token, signal, query } = options;

  let url = `${API_BASE}${path}`;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) params.set(key, String(value));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }

  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const auth = token !== undefined ? token : getToken();
  if (auth) headers["Authorization"] = `Bearer ${auth}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      signal,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, { code: "network_error", message: "Could not reach the server." });
  }

  if (response.status === 204) return undefined as T;

  let data: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }

  if (!response.ok) {
    const body = (data as { error?: ApiErrorBody })?.error ?? {
      code: "http_error",
      message: `Request failed (${response.status}).`,
    };
    throw new ApiError(response.status, body);
  }
  return data as T;
}

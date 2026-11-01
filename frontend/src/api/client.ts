// The only module that talks to the backend. The access token lives in memory only;
// the refresh token is an HttpOnly cookie the page cannot read (spec 14.1).

export const ROLES = ["student", "teacher", "coach", "admin"] as const;
export type Role = (typeof ROLES)[number];

export interface User {
  id: number;
  email: string;
  full_name: string;
  roles: Role[];
  is_active: boolean;
  two_factor_enabled?: boolean;
  consent_version?: string | null;
}

interface TokenResponse {
  access_token: string;
  expires_in: number;
  user: User;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail?: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

// Must match CSRF_HEADER / CSRF_VALUE in backend/app/api/auth.py.
const CSRF_HEADERS = { "X-Requested-With": "kod-izi" };

let accessToken: string | null = null;
let pendingRefresh: Promise<User | null> | null = null;

async function parse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function login(email: string, password: string, otp?: string): Promise<User> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(otp ? { email, password, otp } : { email, password }),
    credentials: "same-origin",
  });
  const data = await parse<TokenResponse>(response);
  accessToken = data.access_token;
  return data.user;
}

async function doRefresh(): Promise<User | null> {
  const response = await fetch("/api/auth/refresh", {
    method: "POST",
    headers: CSRF_HEADERS,
    credentials: "same-origin",
  });
  if (response.status === 401) {
    accessToken = null;
    return null;
  }
  const data = await parse<TokenResponse>(response);
  accessToken = data.access_token;
  return data.user;
}

/** Get a new access token from the refresh cookie. Concurrent callers share one request. */
export function refresh(): Promise<User | null> {
  pendingRefresh ??= doRefresh().finally(() => {
    pendingRefresh = null;
  });
  return pendingRefresh;
}

export async function logout(): Promise<void> {
  accessToken = null;
  await fetch("/api/auth/logout", {
    method: "POST",
    headers: CSRF_HEADERS,
    credentials: "same-origin",
  });
}

function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  return fetch(path, { ...init, headers, credentials: "same-origin" });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response = await authorizedFetch(path, init);
  if (response.status === 401 && (await refresh())) {
    response = await authorizedFetch(path, init);
  }
  return parse<T>(response);
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function apiSend<T>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function apiUpload<T>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  for (const [name, value] of Object.entries(fields)) form.append(name, value);
  return request<T>(path, { method: "POST", body: form });
}

/** Download a file from an authorized endpoint (e.g. a CSV export). */
export async function downloadFile(path: string, filename: string): Promise<void> {
  let response = await authorizedFetch(path);
  if (response.status === 401 && (await refresh())) response = await authorizedFetch(path);
  if (!response.ok) throw new ApiError(response.status);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/** Error code from a 422 response with {detail: {code, message}}, if any. */
export function errorCode(error: unknown): string | undefined {
  if (error instanceof ApiError && error.detail && typeof error.detail === "object") {
    return (error.detail as { code?: string }).code;
  }
  return error instanceof ApiError ? String(error.detail ?? "") : undefined;
}

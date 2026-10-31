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
}

interface TokenResponse {
  access_token: string;
  expires_in: number;
  user: User;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | undefined;

  constructor(status: number, detail?: string) {
    super(detail ?? `HTTP ${status}`);
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
    let detail: string | undefined;
    try {
      detail = ((await response.json()) as { detail?: string }).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export async function login(email: string, password: string): Promise<User> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
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

export async function apiGet<T>(path: string): Promise<T> {
  let response = await authorizedFetch(path);
  if (response.status === 401 && (await refresh())) {
    response = await authorizedFetch(path);
  }
  return parse<T>(response);
}

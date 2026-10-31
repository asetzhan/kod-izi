import { vi } from "vitest";

type Handler = (init: RequestInit | undefined) => unknown;

export function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Stub fetch with a table of "METHOD /path" → handler. A handler returns a Response
 * or a plain value (sent as 200 JSON). Unknown requests fail the test loudly.
 */
export function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${init?.method ?? "GET"} ${url.pathname}${url.search}`;
    const handler = routes[key];
    if (!handler) throw new Error(`unexpected request ${key}`);
    const result = handler(init);
    return result instanceof Response ? result : json(200, result);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

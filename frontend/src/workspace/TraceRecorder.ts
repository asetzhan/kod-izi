// Digital trace in the browser (ФТ-25). Events are kept in localStorage until the server
// confirms them, so nothing is lost when the network or the server is down (spec 13).

import { ApiError, apiSend } from "../api/client";

export type ClientEventKind = "snapshot" | "paste" | "focus_lost" | "focus_back";

export interface ClientEvent {
  seq: number;
  kind: ClientEventKind;
  client_ts: string;
  payload: Record<string, unknown>;
}

export type SendEvents = (sessionId: string, events: ClientEvent[]) => Promise<unknown>;

export const sendEvents: SendEvents = (sessionId, events) =>
  apiSend("POST", `/api/sessions/${sessionId}/events`, { events });

// Keys include the user id: on a shared computer one student's code is never sent
// under, or shown to, another account; logout removes the user's keys.
const PREFIX = "kod-izi.trace.";

function keyFor(userId: number, sessionId: string): string {
  return `${PREFIX}${userId}.${sessionId}`;
}
const BATCH = 200;

interface Stored {
  next: number;
  pending: ClientEvent[];
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function load(key: string): Stored {
  try {
    const raw = storage()?.getItem(key);
    if (raw) return JSON.parse(raw) as Stored;
  } catch {
    // Corrupted entry: start empty.
  }
  return { next: 1, pending: [] };
}

export class TraceRecorder {
  private state: Stored;
  private sending = false;
  private timer: ReturnType<typeof setInterval> | null = null;
  closed = false;

  private readonly key: string;

  constructor(
    readonly userId: number,
    readonly sessionId: string,
    private readonly send: SendEvents,
    private readonly onClosed: () => void = () => undefined,
  ) {
    this.key = keyFor(userId, sessionId);
    this.state = load(this.key);
  }

  get pendingCount(): number {
    return this.state.pending.length;
  }

  record(kind: ClientEventKind, payload: Record<string, unknown> = {}): void {
    this.state.pending.push({
      seq: this.state.next,
      kind,
      client_ts: new Date().toISOString(),
      payload,
    });
    this.state.next += 1;
    this.persist();
  }

  async flush(): Promise<void> {
    if (this.sending || this.state.pending.length === 0) return;
    this.sending = true;
    const batch = this.state.pending.slice(0, BATCH);
    try {
      const result = (await this.send(this.sessionId, batch)) as { session_closed?: boolean };
      const sent = new Set(batch.map((e) => e.seq));
      this.state.pending = this.state.pending.filter((e) => !sent.has(e.seq));
      this.persist();
      if (result?.session_closed) this.markClosed();
    } catch (error) {
      if (error instanceof ApiError && (error.status === 409 || error.status === 403)) {
        // The server keeps everything recorded before closing; the rest is refused.
        this.state.pending = [];
        this.persist();
        this.markClosed();
      }
      // Other errors: keep the events and try again on the next flush.
    } finally {
      this.sending = false;
    }
  }

  start(intervalMs = 3000): void {
    this.timer ??= setInterval(() => void this.flush(), intervalMs);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private markClosed(): void {
    if (!this.closed) {
      this.closed = true;
      this.onClosed();
    }
  }

  private persist(): void {
    try {
      const store = storage();
      if (!store) return;
      if (this.state.pending.length === 0 && this.closed) store.removeItem(this.key);
      else store.setItem(this.key, JSON.stringify(this.state));
    } catch {
      // Storage full or unavailable: events stay in memory only.
    }
  }
}

function keysOf(userId: number): string[] {
  const store = storage();
  if (!store) return [];
  const prefix = `${PREFIX}${userId}.`;
  const keys: string[] = [];
  for (let i = 0; i < store.length; i += 1) {
    const key = store.key(i);
    if (key?.startsWith(prefix)) keys.push(key);
  }
  return keys;
}

/** Send what this user's earlier sessions (closed tab, reload) left unsent. */
export async function flushLeftovers(
  send: SendEvents,
  userId: number,
  currentSessionId: string,
): Promise<void> {
  const prefix = `${PREFIX}${userId}.`;
  for (const key of keysOf(userId)) {
    const sessionId = key.slice(prefix.length);
    if (sessionId === currentSessionId) continue;
    const recorder = new TraceRecorder(userId, sessionId, send);
    recorder.closed = true; // finished sessions are removed once empty
    await recorder.flush();
    if (recorder.pendingCount === 0) storage()?.removeItem(key);
  }
}

/** On logout: try to send the user's unsent events, then remove them from the browser. */
export async function clearUserTrace(send: SendEvents, userId: number): Promise<void> {
  try {
    await flushLeftovers(send, userId, "");
  } finally {
    for (const key of keysOf(userId)) storage()?.removeItem(key);
  }
}

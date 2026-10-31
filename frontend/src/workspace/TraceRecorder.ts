// Digital trace in the browser (ФТ-25). Events are kept in localStorage until the server
// confirms them, so nothing is lost when the network or the server is down (spec 13).

import { ApiError } from "../api/client";

export type ClientEventKind = "snapshot" | "paste" | "focus_lost" | "focus_back";

export interface ClientEvent {
  seq: number;
  kind: ClientEventKind;
  client_ts: string;
  payload: Record<string, unknown>;
}

export type SendEvents = (sessionId: string, events: ClientEvent[]) => Promise<unknown>;

const PREFIX = "kod-izi.trace.";
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

function load(sessionId: string): Stored {
  try {
    const raw = storage()?.getItem(PREFIX + sessionId);
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

  constructor(
    readonly sessionId: string,
    private readonly send: SendEvents,
    private readonly onClosed: () => void = () => undefined,
  ) {
    this.state = load(sessionId);
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
      if (error instanceof ApiError && error.status === 409) {
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
      if (this.state.pending.length === 0 && this.closed) store.removeItem(PREFIX + this.sessionId);
      else store.setItem(PREFIX + this.sessionId, JSON.stringify(this.state));
    } catch {
      // Storage full or unavailable: events stay in memory only.
    }
  }
}

/** Send what earlier sessions (closed tab, reload) left unsent. */
export async function flushLeftovers(send: SendEvents, currentSessionId: string): Promise<void> {
  const store = storage();
  if (!store) return;
  const ids: string[] = [];
  for (let i = 0; i < store.length; i += 1) {
    const key = store.key(i);
    if (key?.startsWith(PREFIX) && key !== PREFIX + currentSessionId) ids.push(key.slice(PREFIX.length));
  }
  for (const id of ids) {
    const recorder = new TraceRecorder(id, send);
    recorder.closed = true; // finished sessions are removed once empty
    await recorder.flush();
    if (recorder.pendingCount === 0) store.removeItem(PREFIX + id);
  }
}

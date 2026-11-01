/** ФТ-28: the trace of a session as the teacher replays it. */

export interface TraceEvent {
  id: number;
  kind: string;
  server_ts: string;
  payload: Record<string, unknown>;
  flagged: boolean;
  stage: string | null;
}

/** The code as it stood after each event: the last code any event carried. */
export function codeTimeline(events: TraceEvent[]): string[] {
  let code = "";
  return events.map((e) => {
    if (typeof e.payload.code === "string") code = e.payload.code;
    return code;
  });
}

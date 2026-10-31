import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/client";
import { clearUserTrace, type ClientEvent, flushLeftovers, TraceRecorder } from "./TraceRecorder";

beforeEach(() => localStorage.clear());

describe("ft25 trace recorder", () => {
  it("ft25: events survive a failed send and a page reload, then are sent once", async () => {
    const failing = vi.fn().mockRejectedValue(new TypeError("network down"));
    const first = new TraceRecorder(7, "s1", failing);
    first.record("snapshot", { code: "int main() {}" });
    first.record("paste", { length: 300, lines: 12 });
    await first.flush();
    expect(first.pendingCount).toBe(2);

    const sent: ClientEvent[][] = [];
    const working = vi.fn(async (_id: string, events: ClientEvent[]) => {
      sent.push(events);
      return { stored: events.length, session_closed: false };
    });
    const afterReload = new TraceRecorder(7, "s1", working);
    afterReload.record("focus_lost");
    await afterReload.flush();
    expect(sent[0]!.map((e) => [e.seq, e.kind])).toEqual([
      [1, "snapshot"],
      [2, "paste"],
      [3, "focus_lost"],
    ]);
    expect(afterReload.pendingCount).toBe(0);
    await afterReload.flush();
    expect(working).toHaveBeenCalledTimes(1);
  });

  it("ft25: a closed session stops the recorder and drops refused events", async () => {
    const onClosed = vi.fn();
    const recorder = new TraceRecorder(7, "s2", async () => {
      throw new ApiError(409, "session_closed");
    }, onClosed);
    recorder.record("focus_back");
    await recorder.flush();
    expect(onClosed).toHaveBeenCalledOnce();
    expect(recorder.closed).toBe(true);
    expect(recorder.pendingCount).toBe(0);
  });

  it("ft25: leftovers of an earlier session are sent with that session's id", async () => {
    const old = new TraceRecorder(7, "old", vi.fn().mockRejectedValue(new TypeError("offline")));
    old.record("snapshot", { code: "x" });
    await old.flush();
    const other = new TraceRecorder(8, "theirs", vi.fn().mockRejectedValue(new TypeError("offline")));
    other.record("snapshot", { code: "someone else's code" });
    await other.flush();
    const send = vi.fn(async () => ({ stored: 1, session_closed: true }));
    await flushLeftovers(send, 7, "new");
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith("old", [expect.objectContaining({ kind: "snapshot" })]);
    expect(localStorage.getItem("kod-izi.trace.7.old")).toBeNull();
    expect(localStorage.getItem("kod-izi.trace.8.theirs")).not.toBeNull();
  });

  it("sec14: logout removes the user's unsent code from the browser", async () => {
    const recorder = new TraceRecorder(7, "s3", vi.fn().mockRejectedValue(new TypeError("offline")));
    recorder.record("snapshot", { code: "secret solution" });
    await recorder.flush();
    await clearUserTrace(vi.fn().mockRejectedValue(new TypeError("offline")), 7);
    expect(Object.keys(localStorage).filter((k) => k.startsWith("kod-izi.trace.7."))).toEqual([]);
  });
});

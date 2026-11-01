import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../../i18n";
import { json, mockApi } from "../../test/fetchMock";
import { codeTimeline } from "../../workspace/replay";
import { MonitoringPage } from "./MonitoringPage";
import { ReplayPage } from "./ReplayPage";

beforeEach(async () => {
  await i18n.changeLanguage("kk");
  vi.unstubAllGlobals();
});

function renderAt(path: string, route: string, element: React.ReactNode) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={route} element={element} />
      </Routes>
    </MemoryRouter>,
  );
}

const EVENTS = [
  { id: 1, kind: "session_start", server_ts: "2030-01-01T10:00:00Z", payload: {}, flagged: false, stage: null },
  { id: 2, kind: "snapshot", server_ts: "2030-01-01T10:02:00Z", payload: { code: "// plan" }, flagged: false, stage: "plan" },
  { id: 3, kind: "snapshot", server_ts: "2030-01-01T10:05:00Z", payload: { code: "int main() {}" }, flagged: false, stage: "code" },
  { id: 4, kind: "test", server_ts: "2030-01-01T10:06:00Z", payload: { per_test: ["OK"] }, flagged: false, stage: "test" },
];

describe("teacher analytics", () => {
  it("ft28: the code is rebuilt for every moment of the session", () => {
    expect(codeTimeline(EVENTS)).toEqual(["", "// plan", "int main() {}", "int main() {}"]);
  });

  it("ft28, ft26: replay moves along the time scale and shows the stage", async () => {
    mockApi({
      "GET /api/sessions/s1/trace": () => ({
        session_id: "s1",
        user_id: 7,
        task_id: 9,
        started_at: "2030-01-01T10:00:00Z",
        events: EVENTS,
      }),
    });
    renderAt("/r/s1", "/r/:sessionId", <ReplayPage />);
    const slider = await screen.findByLabelText("Уақыт шкаласындағы орын");
    await userEvent.click(screen.getByRole("button", { name: /5\.0′ Код/ }));
    expect(screen.getByLabelText("Осы сәттегі код")).toHaveTextContent("int main() {}");
    expect(slider).toHaveValue("2");
    expect(screen.getAllByText(/Кодтау/).length).toBeGreaterThan(0);
  });

  it("ft04, ft20, ft05: board, flagged task and an individual assignment", async () => {
    let assigned: Record<string, unknown> | null = null;
    mockApi({
      "GET /api/courses/3/monitoring": () => ({
        criteria: { correctness: { low: 2, high: 1 } },
        difficulties: { verdicts: { WA: 3 }, compile_error_kinds: { missing_semicolon: 2 }, low_criteria: { correctness: 2 } },
        students: [{ user_id: 7, full_name: "Айгерім", submissions: 3, solved: 1, criteria: { correctness: "low" } }],
      }),
      "GET /api/courses/3/solve-rates": () => ({
        settings: { tolerance: 0.25, min_students: 10 },
        reference: {},
        tasks: [{ task_id: 9, title: "Жұп па?", level: "I", students: 12, solved: 3, rate: 0.25, expected: 0.9894, flagged: true, direction: "harder" }],
      }),
      "GET /api/courses/3/assignments": () => [],
      "GET /api/tasks?course_id=3&status=approved": () => [{ id: 9, title: "Жұп па?" }],
      "POST /api/courses/3/assignments": (init) => {
        assigned = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return json(201, {});
      },
    });
    renderAt("/m/3", "/m/:courseId", <MonitoringPage />);
    expect(await screen.findByText(/«Функционалдық дұрыстық» критерийі бойынша төмен деңгей: 2|төмен деңгей: 2/)).toBeInTheDocument();
    expect(await screen.findByText("Деңгейіне қарағанда қиын")).toBeInTheDocument();
    await userEvent.selectOptions(await screen.findByLabelText("Студент"), "7");
    await userEvent.selectOptions(screen.getByLabelText("Есеп"), "9");
    await userEvent.click(screen.getByRole("button", { name: "Тағайындау" }));
    await waitFor(() => expect(assigned).toMatchObject({ user_id: 7, task_id: 9, genai_mode: "hints_only" }));
  });
});

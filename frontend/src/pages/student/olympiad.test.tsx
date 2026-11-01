import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OlympiadOverview, Problem, Standings } from "../../api/olympiad";
import type { WorkSession } from "../../api/types";
import type { CodeEditorProps } from "../../components/CodeEditor";
import { AuthContext } from "../../auth/AuthContext";
import i18n from "../../i18n";
import { json, mockApi } from "../../test/fetchMock";
import { ContestsPage, StandingsTable } from "./ContestPages";
import { ProblemExtras, StressPanel } from "./OlympiadTools";
import { OlympiadPage } from "./OlympiadPage";
import { WorkspacePage } from "./WorkspacePage";

vi.mock("../../components/CodeEditor", () => ({
  CodeEditor: ({ value, onChange, label }: CodeEditorProps) => (
    <textarea aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}));

const AUTH = {
  user: { id: 7, email: "s@example.com", full_name: "S", roles: ["student" as const], is_active: true },
  loading: false,
  signIn: async () => AUTH.user,
  signOut: async () => undefined,
};

const TASK = {
  id: 9,
  title: "Станоктар",
  level: "III" as const,
  statement_md: "Ең аз уақытты табыңыз.",
  input_format: "",
  output_format: "",
  time_limit_ms: 1000,
  memory_limit_kb: 16384,
  source_url: null,
  examples: [],
};

const OVERVIEW: OlympiadOverview = {
  unlock: { unlocked: true, required: [], missing: [] },
  courses: [
    {
      id: 2,
      title: "Быстрый старт",
      url: "https://stepik.org/course/64454/syllabus",
      topics: [
        {
          id: 5,
          code: "4.1.1",
          title: "Базалық алгоритмдер",
          lessons: [{ title: "Бинарный поиск", url: "https://stepik.org/lesson/307318/step/1", kind: "lecture" }],
          resources: [{ name: "e-maxx", url: "http://e-maxx.ru/algo/", purpose: "" }],
        },
      ],
    },
  ],
  practice: { rules: ["Есепке кемінде бір сағат"], resources: [] },
};

const PROBLEM = {
  id: 9,
  course_id: 2,
  topic_id: 5,
  title: "Станоктар",
  level: "III" as const,
  cf_rating: 1000,
  tags: ["binary search"],
  time_limit_ms: 1000,
  memory_limit_kb: 16384,
  solved: false,
};

beforeEach(async () => {
  await i18n.changeLanguage("kk");
  vi.unstubAllGlobals();
});

function renderAt(path: string, route: string, element: React.ReactNode) {
  render(
    <AuthContext.Provider value={AUTH}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("olympiad part", () => {
  it("ot10, ot04, ot01: reference, recommendations and the bank", async () => {
    mockApi({
      "GET /api/olympiad": () => OVERVIEW,
      "GET /api/olympiad/recommendations": () => ({ rating: 800, range: [900, 1100], problems: [PROBLEM] }),
      "GET /api/olympiad/problems": () => [PROBLEM, { ...PROBLEM, id: 10, title: "Рюкзак", solved: true }],
    });
    renderAt("/o", "/o", <OlympiadPage />);
    expect(await screen.findByRole("link", { name: "Бинарный поиск" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "e-maxx" })).toBeInTheDocument();
    expect(await screen.findByText(/Ұсыныс аралығы: 900–1100/)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Рюкзак" })).toHaveAttribute(
      "href",
      "/student/olympiad/problems/10",
    );
  });

  it("ot01: a locked part 2 says which topics to master", async () => {
    mockApi({
      "GET /api/olympiad": () => ({ ...OVERVIEW, unlock: { unlocked: false, required: [], missing: ["1.11", "1.12"] } }),
    });
    renderAt("/o", "/o", <OlympiadPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("1.11, 1.12");
    expect(screen.queryByText("Есептер банкі")).not.toBeInTheDocument();
  });

  it("ot02: frozen ICPC standings hide names of others", async () => {
    const standings: Standings = {
      format: "icpc",
      frozen: true,
      virtual: false,
      tasks: [{ id: 1, label: "A" }],
      rows: [
        { rank: 1, me: false, virtual: false, name: null, solved: 1, penalty: 30, score: 0, cells: [{ solved: true, wrong: 0, minute: 30, score: 0, pending: 0, tried: true }] },
        { rank: 2, me: true, virtual: false, name: null, solved: 0, penalty: 0, score: 0, cells: [{ solved: false, wrong: 1, minute: null, score: 0, pending: 1, tried: true }] },
      ],
    };
    mockApi({ "GET /api/contests/4/standings": () => standings });
    renderAt("/c", "/c", <StandingsTable contestId={4} />);
    expect(await screen.findByRole("status")).toHaveTextContent("кесте тоқтатылды");
    expect(screen.getByText("Қатысушы 1")).toBeInTheDocument();
    expect(screen.getByText("Сіз")).toBeInTheDocument();
    expect(screen.getByText("? −1")).toBeInTheDocument();
  });

  it("ot03: a finished contest can be written virtually", async () => {
    let started = false;
    const contest = {
      id: 4,
      course_id: 2,
      title: "СПбГУ 1",
      format: "icpc",
      starts_at: "2026-01-01T10:00:00Z",
      ends_at: "2026-01-01T12:00:00Z",
      freeze_minutes: 60,
      penalty_minutes: 20,
      task_count: 3,
      state: "finished",
      task_ids: [],
      my_virtual: null,
    };
    mockApi({
      "GET /api/contests": () =>
        started ? [{ ...contest, my_virtual: { started_at: "2026-11-01T10:00:00Z", ends_at: "2026-11-01T12:00:00Z" } }] : [contest],
      "POST /api/contests/4/virtual": () => {
        started = true;
        return json(201, {});
      },
    });
    renderAt("/c", "/c", <ContestsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Виртуалды жазу" }));
    expect(await screen.findByText(/Виртуалды жарыс/)).toBeInTheDocument();
    expect(started).toBe(true);
  });

  it("ot06: the stress test shows the input where answers differ", async () => {
    const fetchMock = mockApi({
      "POST /api/sessions/s1/stress": () => ({
        status: "mismatch",
        iterations: 3,
        input: "case 3\n",
        expected: "6\n",
        actual: "5\n",
        detail: "",
      }),
    });
    renderAt("/s", "/s", <StressPanel sessionId="s1" code="int main() {}" disabled={false} />);
    await userEvent.type(screen.getByLabelText("Баяу дұрыс шешім"), "brute");
    await userEvent.type(screen.getByLabelText("Тест генераторы"), "gen");
    await userEvent.click(screen.getByRole("button", { name: "Стресс-тестті іске қосу" }));
    expect(await screen.findByText("3-тестте жауаптар әртүрлі")).toBeInTheDocument();
    expect(screen.getByText("case 3")).toBeInTheDocument();
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as Record<string, unknown>;
    expect(body).toMatchObject({ code: "int main() {}", brute_code: "brute", generator_code: "gen" });
  });

  it("ot05: the tutorial waits an hour and hints come step by step", async () => {
    let problem: Problem = {
      task: TASK,
      tags: [],
      cf_rating: 1000,
      solved: false,
      minutes_spent: 12,
      editorial_available: false,
      editorial_opens_at: "2030-01-01T11:00:00Z",
      editorial_md: null,
      hints: [],
      next_hint_level: 1,
      next_hint_at: null,
      in_contest: false,
    };
    mockApi({
      "GET /api/olympiad/problems/9": () => problem,
      "POST /api/olympiad/problems/9/hints": () => {
        const hint = { level: 1, answer: "Екілік іздеу", blocked: false, created_at: "2030-01-01T10:00:00Z" };
        problem = { ...problem, hints: [hint], next_hint_level: 2, next_hint_at: "2030-01-01T10:15:00Z" };
        return json(201, hint);
      },
    });
    renderAt("/p", "/p", <ProblemExtras taskId={9} sessionId="s1" code="" language="kk" />);
    expect(await screen.findByText(/бір сағат жұмсағаннан кейін/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Келесі кеңес: Бағыт" }));
    expect(await screen.findByText(/Екілік іздеу/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Келесі кеңес: Идея" })).toBeDisabled();
  });

  it("ot02: a contest problem is submitted without explanation and without the assistant", async () => {
    const session: WorkSession = {
      session_id: "s1",
      assessment_id: 4,
      genai_mode: "forbidden",
      ends_at: null,
      code: "int main() {}",
      task: TASK,
    };
    const fetchMock = mockApi({
      "POST /api/sessions": () => json(201, session),
      "POST /api/sessions/s1/events": () => ({ accepted: 0 }),
      "GET /api/olympiad/problems/9/my-tests": () => [],
      "POST /api/sessions/s1/submit": () =>
        json(201, {
          id: 1,
          task_id: 9,
          assessment_id: 4,
          status: "done",
          verdict: "OK",
          tests_passed: 2,
          tests_total: 2,
          max_time_ms: 1,
          max_memory_kb: 1,
          compile_output: "",
          results: [],
          created_at: "2030-01-01T10:00:00Z",
          explanation: null,
          questions: [],
        }),
    });
    renderAt("/student/contests/4/tasks/9", "/student/contests/:assessmentId/tasks/:taskId", <WorkspacePage olympiad />);
    expect(await screen.findByText("Өз тесттерім")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Түсіндірме/)).not.toBeInTheDocument();
    expect(screen.queryByText("Талдау және кеңестер")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Тапсыру" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/submit"))).toBe(true),
    );
    const submit = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/submit"));
    expect(JSON.parse(String(submit?.[1]?.body))).not.toHaveProperty("explanation");
  });
});

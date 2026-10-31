import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SubmissionResult, WorkSession } from "../../api/types";
import type { CodeEditorProps } from "../../components/CodeEditor";
import i18n from "../../i18n";
import { mockApi } from "../../test/fetchMock";
import { AuthContext } from "../../auth/AuthContext";
import { WorkspacePage } from "./WorkspacePage";

const AUTH = {
  user: { id: 7, email: "s@example.com", full_name: "S", roles: ["student" as const], is_active: true },
  loading: false,
  signIn: async () => AUTH.user,
  signOut: async () => undefined,
};

// Monaco does not run in jsdom: a textarea stands in for the editor.
vi.mock("../../components/CodeEditor", () => ({
  CodeEditor: ({ value, onChange, onPaste, label }: CodeEditorProps) => (
    <textarea
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onPaste={(e) => {
        const text = e.clipboardData.getData("text");
        onPaste(text.length, text.split("\n").length);
      }}
    />
  ),
}));

const SESSION: WorkSession = {
  session_id: "11111111-1111-1111-1111-111111111111",
  assessment_id: 3,
  ends_at: "2030-01-01T10:00:00Z",
  code: "",
  task: {
    id: 9,
    title: "Жұп немесе тақ",
    level: "I",
    statement_md: "n санын тексеріңіз.",
    input_format: "Бір бүтін сан.",
    output_format: "EVEN немесе ODD.",
    time_limit_ms: 1000,
    memory_limit_kb: 262144,
    source_url: null,
    examples: [{ position: 1, input: "4\n", expected_output: "EVEN\n" }],
  },
};

const QUEUED: SubmissionResult = {
  id: 50,
  task_id: 9,
  assessment_id: 3,
  status: "queued",
  verdict: null,
  tests_passed: 0,
  tests_total: 3,
  max_time_ms: null,
  max_memory_kb: null,
  compile_output: "",
  results: [],
  created_at: "2030-01-01T09:00:00Z",
  explanation: "n % 2",
  questions: [
    { question: "Циклыңыз қай кезде тоқтайды?", answer: null },
    { question: "Қандай тесттермен тексердіңіз?", answer: null },
  ],
};

beforeEach(async () => {
  localStorage.clear();
  await i18n.changeLanguage("kk");
});

function renderPage() {
  render(
    <AuthContext.Provider value={AUTH}>
      <MemoryRouter initialEntries={["/student/assessments/3/tasks/9"]}>
        <Routes>
          <Route path="/student/assessments/:assessmentId/tasks/:taskId" element={<WorkspacePage />} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("ft24 workspace", () => {
  it("ft24: student writes code, runs it with own input and sees the output", async () => {
    let runBody: unknown;
    mockApi({
      "POST /api/sessions": () => SESSION,
      [`POST /api/sessions/${SESSION.session_id}/events`]: () => ({ stored: 1, session_closed: false }),
      [`POST /api/sessions/${SESSION.session_id}/run`]: (init) => {
        runBody = JSON.parse(String(init?.body));
        return { status: "finished", stdout: "EVEN\n", stderr: "", compile_output: "", time_ms: 3, memory_kb: 800 };
      },
    });
    renderPage();
    const user = userEvent.setup();
    const editor = await screen.findByLabelText("C++ редакторы");
    expect(screen.getByText("n санын тексеріңіз.")).toBeInTheDocument();
    await user.type(editor, "int main(){{}");
    await user.type(screen.getByLabelText("Өз енгізуіңіз (stdin)"), "4");
    await user.click(screen.getByRole("button", { name: "Іске қосу" }));
    expect(await screen.findByText("Бағдарлама аяқталды · 3 ms")).toBeInTheDocument();
    expect(runBody).toEqual({ code: "int main(){}", stdin: "4" });
  });

  it("ft27: submission shows the verdict and asks questions about own code", async () => {
    let answers: unknown;
    mockApi({
      "POST /api/sessions": () => ({ ...SESSION, code: "int main(){}" }),
      [`POST /api/sessions/${SESSION.session_id}/events`]: () => ({ stored: 1, session_closed: false }),
      [`POST /api/sessions/${SESSION.session_id}/submit`]: () => QUEUED,
      "GET /api/submissions/50": () => ({ ...QUEUED, status: "done", verdict: "OK", tests_passed: 3 }),
      "PUT /api/submissions/50/answers": (init) => {
        answers = JSON.parse(String(init?.body));
        return { ...QUEUED, status: "done", verdict: "OK", tests_passed: 3 };
      },
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(/Шешіміңізді түсіндіріңіз/), "n % 2 тексеремін");
    await user.click(screen.getByRole("button", { name: "Тапсыру" }));
    expect(await screen.findByText("Кезекте…")).toBeInTheDocument();
    expect(await screen.findByText("OK — дұрыс", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText(/3\/3 тест өтті/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Циклыңыз қай кезде тоқтайды?"), "n = 0 болғанда");
    await user.type(screen.getByLabelText("Қандай тесттермен тексердіңіз?"), "0, 7, -3");
    await user.click(screen.getByRole("button", { name: "Жауаптарды жіберу" }));
    await waitFor(() => expect(answers).toEqual({ answers: ["n = 0 болғанда", "0, 7, -3"] }));
  });

  it("ft29: a paste is recorded in the trace with its size", async () => {
    const batches: unknown[] = [];
    mockApi({
      "POST /api/sessions": () => SESSION,
      [`POST /api/sessions/${SESSION.session_id}/events`]: (init) => {
        batches.push(JSON.parse(String(init?.body)));
        return { stored: 1, session_closed: false };
      },
      [`POST /api/sessions/${SESSION.session_id}/test`]: () => ({ compile_output: "", results: [] }),
    });
    renderPage();
    const user = userEvent.setup();
    const editor = await screen.findByLabelText("C++ редакторы");
    await user.click(editor);
    await user.paste("x".repeat(250));
    await user.click(screen.getByRole("button", { name: "Ашық тесттер" }));
    await waitFor(() => {
      const events = batches.flatMap((b) => (b as { events: { kind: string; payload: object }[] }).events);
      expect(events).toContainEqual(expect.objectContaining({ kind: "paste", payload: { length: 250, lines: 1 } }));
      expect(events).toContainEqual(expect.objectContaining({ kind: "snapshot" }));
    });
  });

  it("sec14: a session opened elsewhere blocks this tab", async () => {
    mockApi({
      "POST /api/sessions": () => SESSION,
      [`POST /api/sessions/${SESSION.session_id}/events`]: () =>
        new Response(JSON.stringify({ detail: "session_closed" }), { status: 409 }),
      [`POST /api/sessions/${SESSION.session_id}/test`]: () => ({ compile_output: "", results: [] }),
    });
    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("C++ редакторы"), "x");
    await user.click(screen.getByRole("button", { name: "Ашық тесттер" }));
    expect(await screen.findByText(/басқа терезеде/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Іске қосу" })).toBeDisabled();
  });
});

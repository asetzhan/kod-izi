import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import type { AiGrade, ComponentEntry, ComponentSummary } from "../../api/types";
import i18n from "../../i18n";
import { mockApi } from "../../test/fetchMock";
import { ResultsPage } from "../student/ResultsPage";
import { ConfirmGrade } from "./ConfirmGrade";
import { ModelPanelPage } from "./ModelPanelPage";

beforeEach(async () => {
  await i18n.changeLanguage("kk");
});

const SUMMARY: ComponentSummary[] = [1, 2, 3, 4, 5].map((n) => ({
  component: n, name: String(n), auto_enabled: true, entries: n === 1 ? 1 : 0,
  by_source: {}, suggestions: n === 1 ? 1 : 0,
}));

const ENTRY: ComponentEntry = {
  id: 7, component: 1, subject_type: "topic", subject_id: 3, key: "goals",
  value: { goal: "Менің мақсатым" }, auto_value: { goal: "Авто" }, source: "auto_edited",
  suggestion: { goal: "Жаңа авто" }, updated_by: 2, updated_at: "2030-01-01T00:00:00Z", versions: 2,
};

describe("ft07 model panel", () => {
  it("ft07: five components around the core; teacher edits and decides on a suggestion", async () => {
    const calls: string[] = [];
    let saved: unknown;
    mockApi({
      "GET /api/courses/1/components": () => SUMMARY,
      "GET /api/courses/1/components/1/entries": () => [ENTRY],
      "PUT /api/entries/7": (init) => {
        saved = JSON.parse(String(init?.body));
        calls.push("edit");
        return ENTRY;
      },
      "POST /api/entries/7/suggestion/reject": () => {
        calls.push("reject");
        return { ...ENTRY, suggestion: null };
      },
      "GET /api/entries/7/versions": () => [
        { version: 1, value: { goal: "Авто" }, source: "auto", author_id: null, note: "generated", created_at: "2030-01-01T00:00:00Z" },
        { version: 2, value: { goal: "Менің мақсатым" }, source: "auto_edited", author_id: 2, note: "edited", created_at: "2030-01-02T00:00:00Z" },
      ],
      "POST /api/entries/7/revert": () => {
        calls.push("revert");
        return ENTRY;
      },
    });
    render(
      <MemoryRouter initialEntries={["/teacher/courses/1/model"]}>
        <Routes>
          <Route path="/teacher/courses/:courseId/model" element={<ModelPanelPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    const diagram = await screen.findByRole("group", { name: "Модель панелі" });
    expect(within(diagram).getAllByRole("button")).toHaveLength(5);
    expect(within(diagram).getByText("Ядро: студенттің программалау әрекеті")).toBeInTheDocument();
    await user.click(within(diagram).getByRole("button", { name: /1\. Педагогикалық-мақсаттық/ }));
    expect(await screen.findByText("автоматтыдан өзгертілген")).toBeInTheDocument();
    expect(screen.getByText(/Жүйенің жаңа ұсынысы/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Өзгерту" }));
    const editor = screen.getByLabelText("Мәні (JSON)");
    await user.clear(editor);
    await user.type(editor, '{{"goal": "Түзетілген"}');
    await user.click(screen.getByRole("button", { name: "Сақтау" }));
    await waitFor(() => expect(saved).toEqual({ value: { goal: "Түзетілген" } }));

    await user.click(screen.getByRole("button", { name: "Бас тарту" }));
    await user.click(screen.getByRole("button", { name: "Нұсқалар (2)" }));
    const restore = await screen.findAllByRole("button", { name: "Осы нұсқаға қайту" });
    await user.click(restore[0]!);
    await waitFor(() => expect(calls).toEqual(["edit", "reject", "revert"]));
  });
});

const AI: AiGrade = {
  id: 4, submission_id: 40, status: "ready",
  criteria: (["understanding", "algorithm", "correctness", "code_quality", "debugging", "explanation"] as const)
    .map((code) => ({ code, level: "high" as const, evidence: [], confidence: 0.7 })),
  components: { F: 100, E: 60, A: 50 }, score: 72.3, interpretation: "", feedback: "AI кері байланысы",
  next_step: "", flags: [], review_reasons: [], model: "m", prompt_version: "p", weights: {},
  fragment_ids: [], attempts: 1, created_at: "2030-01-01T00:00:00Z",
};

describe("ft03 confirm grade", () => {
  it("ft03: a changed level needs a reason; the form sends levels and components", async () => {
    let body: Record<string, unknown> | undefined;
    mockApi({
      "GET /api/submissions/40/teacher-grade": () => null,
      "POST /api/submissions/40/teacher-grade": (init) => {
        body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return { id: 1 };
      },
    });
    render(<ConfirmGrade submissionId={40} ai={AI} />);
    const user = userEvent.setup();
    expect(screen.getByLabelText("Студентке кері байланыс")).toHaveValue("AI кері байланысы");
    expect(screen.getByLabelText(/Түзету себебі/)).not.toBeRequired();
    await user.selectOptions(screen.getByLabelText("Код сапасы"), "mid");
    expect(screen.getByLabelText(/Түзету себебі/)).toBeRequired();
    await user.type(screen.getByLabelText(/Түзету себебі/), "Атаулар түсініксіз");
    await user.click(screen.getByRole("button", { name: "Растау" }));
    await waitFor(() => expect(body?.reason).toBe("Атаулар түсініксіз"));
    expect((body?.levels as Record<string, string>).code_quality).toBe("mid");
    expect(body?.components).toEqual({ F: 100, E: 60, A: 50 });
  });
});

describe("ft41 student results", () => {
  it("ft41: confirmed result shows levels, AI marking and book references", async () => {
    mockApi({
      "GET /api/my/results": () => [{
        submission_id: 40, task_id: 9, score: 72.3, feedback: "Шартты қайта қараңыз.",
        feedback_source: "ai", book_refs: ["C++ негіздері, 4.2-бөлім, 67-бет"], next_step: "",
        confirmed_at: "2030-01-01T00:00:00Z",
        criteria: [{ code: "correctness", name: "Функционалдық дұрыстық", level: "high",
                     interpretation: "Барлық тест өтеді" }],
      }],
      "GET /api/courses": () => [],
    });
    render(<ResultsPage />);
    expect(await screen.findByText("AI · алдын ала")).toBeInTheDocument();
    expect(screen.getByText(/67-бет/)).toBeInTheDocument();
    expect(screen.getByText("Барлық тест өтеді")).toBeInTheDocument();
  });
});

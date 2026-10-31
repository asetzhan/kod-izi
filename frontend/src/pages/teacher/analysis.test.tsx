import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import type { AiGrade, Rubric } from "../../api/types";
import i18n from "../../i18n";
import { mockApi } from "../../test/fetchMock";
import { AssistantPanel } from "../student/AssistantPanel";
import { MaterialsPage } from "./MaterialsPage";
import { RubricPage } from "./RubricPage";
import { SubmissionReviewPage } from "./SubmissionReviewPage";

beforeEach(async () => {
  await i18n.changeLanguage("kk");
});

function at(path: string, route: string, element: React.ReactNode) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={route} element={element} />
      </Routes>
    </MemoryRouter>,
  );
}

const RUBRIC: Rubric = {
  weight_f: 0.3626,
  weight_e: 0.3641,
  weight_a: 0.2733,
  component_scales: { F: "f", E: "e", A: "a" },
  criteria: [
    { code: "correctness", name: "Функционалдық дұрыстық", indicators: "", data_sources: "",
      descriptor_low: "l", descriptor_mid: "m", descriptor_high: "h" },
  ],
};

describe("ft15 rubric page", () => {
  it("ft15: teacher changes weights and saves; a wrong sum is shown", async () => {
    let saved: Rubric | undefined;
    mockApi({
      "GET /api/courses/1/rubric": () => RUBRIC,
      "PUT /api/courses/1/rubric": (init) => {
        saved = JSON.parse(String(init?.body)) as Rubric;
        return saved;
      },
    });
    at("/teacher/courses/1/rubric", "/teacher/courses/:courseId/rubric", <RubricPage />);
    const user = userEvent.setup();
    const f = await screen.findByLabelText("F — функционалдық дұрыстық");
    await user.clear(f);
    await user.type(f, "0.5");
    expect(screen.getByRole("alert")).toHaveTextContent("1 болуы керек");
    await user.click(screen.getByRole("button", { name: "Сақтау" }));
    await waitFor(() => expect(saved?.weight_f).toBe(0.5));
  });
});

describe("ft06 materials page", () => {
  it("ft06: upload needs the rights confirmation and sends the form fields", async () => {
    let form: FormData | undefined;
    mockApi({
      "GET /api/courses/1/materials": () => [],
      "GET /api/courses/1": () => ({ id: 1, title: "C++", part: "part1", source_url: null,
        description: "", can_edit: true, topics: [] }),
      "GET /api/tasks?course_id=1": () => [],
      "POST /api/courses/1/materials": (init) => {
        form = init?.body as FormData;
        return { id: 3, course_id: 1, title: "Кітап", author: "", kind: "book", versions: [] };
      },
    });
    at("/teacher/courses/1/materials", "/teacher/courses/:courseId/materials", <MaterialsPage />);
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Файл"), new File(["%PDF-"], "b.pdf"));
    await user.type(screen.getByLabelText("Атауы"), "Кітап");
    const submit = screen.getByRole("button", { name: "Жүктеу" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByLabelText(/құқығым бар екенін растаймын/));
    await user.click(submit);
    await waitFor(() => expect(form?.get("rights_confirmed")).toBe("true"));
    expect(form?.get("title")).toBe("Кітап");
  });
});

const GRADE: AiGrade = {
  id: 1, submission_id: 40, status: "needs_review",
  criteria: [{ code: "correctness", level: "mid", confidence: 0.6, evidence: [
    { type: "book", ref: "C++ негіздері, 2-бөлім, 2-бет", quote: "n % 2" }] }],
  components: { F: 67, E: 50, A: 40 }, score: 53.4, interpretation: "", feedback: "Шартты қайта қараңыз",
  next_step: "", flags: ["possible_injection"], review_reasons: ["possible_injection: student_code"],
  model: "llama3.1:8b", prompt_version: "assessment-v1-draft", weights: {}, fragment_ids: [11, 12],
  attempts: 1, created_at: "2030-01-01T00:00:00Z",
};

describe("ft35 submission review", () => {
  it("ft35: the teacher opens the book fragment the grade cites", async () => {
    mockApi({
      "GET /api/submissions/40": () => ({ id: 40, task_id: 9, assessment_id: 3, status: "done", verdict: "WA",
        tests_passed: 2, tests_total: 3, max_time_ms: 1, max_memory_kb: 1, compile_output: "", results: [],
        created_at: "2030-01-01T00:00:00Z", explanation: "n % 2", questions: [] }),
      "GET /api/submissions/40/ai-grades": () => [GRADE],
      "GET /api/chunks/11": () => ({ id: 11, material_id: 3, material_title: "C++ негіздері", version: 1,
        chapter: "1-бөлім", page: 1, text: "Кіріспе" }),
      "GET /api/chunks/12": () => ({ id: 12, material_id: 3, material_title: "C++ негіздері", version: 1,
        chapter: "2-бөлім", page: 2, text: "Жұп сан n % 2 == 0 тексеріледі." }),
    });
    at("/teacher/submissions/40", "/teacher/submissions/:submissionId", <SubmissionReviewPage />);
    expect(await screen.findByText(/бағаға әсер ету әрекеті/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "C++ негіздері, 2-бөлім, 2-бет" }));
    expect(await screen.findByText("Жұп сан n % 2 == 0 тексеріледі.")).toBeInTheDocument();
  });
});

describe("ft47 assistant panel", () => {
  it("ft47: hidden when the assessment forbids AI", () => {
    const { container } = render(<AssistantPanel sessionId="s" mode="forbidden" code="" disabled={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("ft47: asks with the current code and shows the answer", async () => {
    let body: unknown;
    let answered = false;
    mockApi({
      "GET /api/sessions/s/assistant": () => (answered ? [{ id: 1, question: "Неге WA?",
        answer: "Шекаралық жағдайды тексеріңіз.", blocked: false, created_at: "" }] : []),
      "POST /api/sessions/s/assistant": (init) => {
        body = JSON.parse(String(init?.body));
        answered = true;
        return { id: 1, question: "Неге WA?", answer: "Шекаралық жағдайды тексеріңіз.", blocked: false, created_at: "" };
      },
    });
    render(<AssistantPanel sessionId="s" mode="hints_only" code="int main(){}" disabled={false} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Сұрағыңыз"), "Неге WA?");
    await user.click(screen.getByRole("button", { name: "Сұрау" }));
    expect(await screen.findByText("Шекаралық жағдайды тексеріңіз.")).toBeInTheDocument();
    expect(body).toEqual({ question: "Неге WA?", code: "int main(){}", ui_language: "kk" });
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { levelFor } from "../../api/levels";
import type { Course, LevelRule, Task } from "../../api/types";
import i18n from "../../i18n";
import { json, mockApi } from "../../test/fetchMock";
import { CoursePage } from "./CoursePage";
import { TaskEditorPage } from "./TaskEditorPage";

const RULE: LevelRule = {
  sum_to_level: [
    { min: 0, max: 2, level: "I" },
    { min: 3, max: 4, level: "II" },
    { min: 5, max: 6, level: "III" },
    { min: 7, max: 8, level: "IV" },
  ],
};

const COURSE: Course = {
  id: 1,
  title: "Введение в программирование (C++)",
  part: "part1",
  source_url: "https://stepik.org/course/363/syllabus",
  description: "",
  can_edit: true,
  topics: [
    {
      id: 10,
      code: "1.3",
      title: "Бүтін сандар",
      position: 3,
      learning_outcomes: "",
      lessons: [
        {
          id: 100,
          stepik_lesson_id: 13021,
          title: "Целые числа",
          url: "https://stepik.org/lesson/13021/step/1",
          kind: "lecture_and_practice",
        },
      ],
      knowledge_components: [{ id: 5, code: "int.io", name: "Енгізу-шығару" }],
    },
  ],
};

const TASK: Task = {
  id: 7,
  course_id: 1,
  topic_id: 10,
  external_key: "EXP-I-1",
  title: "Жұп немесе тақ",
  level: "I",
  level_status: "suggested",
  status: "draft",
  statement_md: "# Жұп немесе тақ",
  input_format: "n",
  output_format: "EVEN/ODD",
  time_limit_ms: 1000,
  memory_limit_kb: 262144,
  reference_solution: "int main() {}",
  reference_language: "cpp17",
  source_url: null,
  source_note: "",
  teacher_requirements: "",
  features: { knowledge_actions: 0, algorithm_freedom: 0, edge_cases: 1, justification: 0 },
  level_rationale: "",
  tests: [{ id: 1, position: 1, input: "4\n", expected_output: "EVEN\n", is_hidden: false }],
  knowledge_component_ids: [5],
};

beforeEach(async () => {
  await i18n.changeLanguage("kk");
});

describe("ft19 level rule", () => {
  it("ft19: boundary totals map to levels as in spec 5.2", () => {
    const scores = (a: number, b: number, c: number, d: number) => ({
      knowledge_actions: a,
      algorithm_freedom: b,
      edge_cases: c,
      justification: d,
    });
    expect(levelFor(RULE, scores(2, 0, 0, 0))).toBe("I");
    expect(levelFor(RULE, scores(2, 1, 0, 0))).toBe("II");
    expect(levelFor(RULE, scores(2, 2, 0, 0))).toBe("II");
    expect(levelFor(RULE, scores(2, 2, 1, 0))).toBe("III");
    expect(levelFor(RULE, scores(2, 2, 2, 0))).toBe("III");
    expect(levelFor(RULE, scores(2, 2, 2, 1))).toBe("IV");
  });

  it("ft19: teacher changes a feature and confirms the level", async () => {
    let sent: unknown;
    mockApi({
      "GET /api/tasks/7": () => TASK,
      "GET /api/courses/1": () => COURSE,
      "GET /api/settings/task-level-rule": () => RULE,
      "PUT /api/tasks/7/level": (init) => {
        sent = JSON.parse(String(init?.body));
        return { ...TASK, level: "II", level_status: "confirmed" };
      },
    });
    render(
      <MemoryRouter initialEntries={["/teacher/tasks/7"]}>
        <Routes>
          <Route path="/teacher/tasks/:taskId" element={<TaskEditorPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    const freedom = await screen.findByLabelText("Алгоритмді таңдау еркіндігі");
    // Editing is enabled once the course (and with it the edit right) has loaded.
    await waitFor(() => expect(freedom).toBeEnabled());
    await user.selectOptions(freedom, "2");
    await waitFor(() => expect(screen.getByTestId("level-preview")).toHaveTextContent("II"));
    await user.click(screen.getByRole("button", { name: "Растау" }));
    expect(await screen.findByText("Деңгей расталды.")).toBeInTheDocument();
    expect(sent).toEqual({
      features: { knowledge_actions: 0, algorithm_freedom: 2, edge_cases: 1, justification: 0 },
      level: null,
      rationale: "",
    });
  });
});

function renderCourse() {
  render(
    <MemoryRouter initialEntries={["/teacher/courses/1"]}>
      <Routes>
        <Route path="/teacher/courses/:courseId" element={<CoursePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ft12 course page", () => {
  it("ft12: topics show their Stepik lesson links", async () => {
    mockApi({
      "GET /api/courses/1": () => COURSE,
      "GET /api/tasks?course_id=1": () => [TASK],
      "GET /api/assessments?course_id=1": () => [],
    });
    renderCourse();
    const link = await screen.findByRole("link", { name: "Целые числа" });
    expect(link).toHaveAttribute("href", "https://stepik.org/lesson/13021/step/1");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: "Жұп немесе тақ" })).toHaveAttribute(
      "href",
      "/teacher/tasks/7",
    );
  });
});

describe("ft22 import", () => {
  it("ft22: a broken archive shows an understandable error", async () => {
    mockApi({
      "GET /api/courses/1": () => COURSE,
      "GET /api/tasks?course_id=1": () => [],
      "GET /api/assessments?course_id=1": () => [],
      "POST /api/courses/1/tasks/import": () =>
        json(422, { detail: { code: "unpaired_test", message: "tests/02.out is missing" } }),
    });
    renderCourse();
    const user = userEvent.setup();
    const input = await screen.findByLabelText("Мұрағат файлы");
    await user.upload(input, new File(["zip"], "task.zip", { type: "application/zip" }));
    await user.click(screen.getByRole("button", { name: "Импорттау" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Тесттің .in немесе .out файлы жетіспейді. (tests/02.out is missing)",
    );
  });
});

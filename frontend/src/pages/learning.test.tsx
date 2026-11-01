import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../i18n";
import { json, mockApi } from "../test/fetchMock";
import { MyProgressPage, StudentProgressPage } from "./ProgressPages";
import { GenerateTask } from "./teacher/GenerateTask";

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

const PROGRESS = {
  next: {
    weakest_criterion: "debugging",
    weak_components: [{ kc_id: 1, name: "Жұптылық", topic_code: "1.4", p_learned: 0.18 }],
    target_level: "II",
    tasks: [{ id: 9, title: "Жұп па?", level: "II" }],
    lessons: [{ title: "Условный оператор", url: "https://stepik.org/lesson/1/step/1" }],
  },
  trajectory: {
    course: "C++",
    results: [
      { at: "2030-01-01T10:00:00Z", task: "Жұп па?", level: "I", assessment: "1-БЖ", score: 72, criteria: {} },
    ],
    components: [
      { kc_id: 1, code: "cond", name: "Жұптылық", topic_code: "1.4", attempts: 2, p_learned: 0.18, mastered: false },
      { kc_id: 2, code: "loop", name: "Цикл", topic_code: "1.5", attempts: 6, p_learned: 0.97, mastered: true },
    ],
    mastered_components: 1,
  },
};

describe("student model and generation", () => {
  it("ft39, ft44, ft45: the student sees the model, the next step and the trajectory", async () => {
    mockApi({ "GET /api/my/progress?course_id=3": () => ({ ...PROGRESS, next: { ...PROGRESS.next, tasks: [] } }) });
    renderAt("/p/3", "/p/:courseId", <MyProgressPage />);
    expect(await screen.findByText(/Ең әлсіз критерий/)).toBeInTheDocument();
    expect(screen.getByText(/Жұптылық \(1\.4, 18%\)/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Условный оператор" })).toBeInTheDocument();
    expect(screen.getByText(/Меңгерілген компоненттер: 1 \/ 2/)).toBeInTheDocument();
    expect(screen.getByText(/1-БЖ · Жұп па\?/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Тағайындау" })).not.toBeInTheDocument();
  });

  it("ft44, ft05: the teacher assigns the suggested task in one click", async () => {
    let body: Record<string, unknown> | null = null;
    mockApi({
      "GET /api/courses/3/students/7/progress": () => PROGRESS,
      "POST /api/courses/3/assignments": (init) => {
        body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return json(201, {});
      },
    });
    renderAt("/s/3/7", "/s/:courseId/:studentId", <StudentProgressPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Тағайындау" }));
    await waitFor(() => expect(body).toEqual({ task_id: 9, user_id: 7 }));
    expect(await screen.findByRole("status")).toHaveTextContent("Тапсырма берілді");
  });

  it("ft21: a draft is generated from a chosen book chapter", async () => {
    let body: Record<string, unknown> | null = null;
    mockApi({
      "GET /api/courses/3/materials": () => [
        { id: 4, course_id: 3, title: "C++ оқулығы", author: "", kind: "book", versions: [{ id: 8, status: "ready" }] },
      ],
      "GET /api/materials/4/versions/8/chapters": () => [
        { chapter: "4. Циклдер", first_page: 60, last_page: 80, chunks: 9 },
      ],
      "POST /api/courses/3/tasks/generate": (init) => {
        body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return json(201, { task: { id: 21, title: "Цикл есебі" }, dropped_tests: 1, notes: [] });
      },
    });
    renderAt(
      "/c",
      "/c",
      <GenerateTask courseId={3} topics={[{ id: 5, code: "1.5", title: "Циклдер" } as never]} />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Тақырып"), "5");
    await userEvent.selectOptions(await screen.findByLabelText("Кітап (міндетті емес)"), "4");
    await userEvent.selectOptions(await screen.findByLabelText("Тарау"), "4. Циклдер");
    await userEvent.click(screen.getByRole("button", { name: "Жобаны жасау" }));
    expect(await screen.findByRole("link", { name: "Цикл есебі" })).toHaveAttribute("href", "/teacher/tasks/21");
    expect(body).toMatchObject({ topic_id: 5, level: "I", version_id: 8, chapter: "4. Циклдер" });
  });
});

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthContext } from "../../auth/AuthContext";
import i18n from "../../i18n";
import { json, mockApi } from "../../test/fetchMock";
import { ContestPage } from "./ContestPages";
import { KnowledgeMapPage } from "./KnowledgeMapPage";

const AUTH = {
  user: { id: 7, email: "s@example.com", full_name: "S", roles: ["student" as const], is_active: true },
  loading: false,
  signIn: async () => AUTH.user,
  signOut: async () => undefined,
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

describe("after the contest and outside the system", () => {
  it("ot09, ot08: knowledge map, rating and linking Codeforces only with consent", async () => {
    let linked: Record<string, unknown> | null = null;
    mockApi({
      "GET /api/my/knowledge-map": () => ({
        topics: [{ tag: "dp", bank: 4, tried: 2, solved: 1, external: 3, mastery: 0.5 }],
        rating: { internal: [{ at: "2030-01-01T10:00:00Z", rating: 1000 }], codeforces: [] },
      }),
      "GET /api/my/external": () => ({ accounts: [], solves: [] }),
      "POST /api/my/external/codeforces": (init) => {
        linked = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return json(201, {});
      },
    });
    renderAt("/k", "/k", <KnowledgeMapPage />);
    expect(await screen.findByText("1/4")).toBeInTheDocument();
    expect(screen.getByText(/Жүйедегі рейтинг: 1000/)).toBeInTheDocument();
    await userEvent.type(await screen.findByLabelText("Codeforces логині (handle)"), "tourist_fan");
    const button = screen.getByRole("button", { name: "Байланыстыру" });
    expect(button).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(button);
    await waitFor(() => expect(linked).toEqual({ handle: "tourist_fan", consent: true }));
  });

  it("ot07: after the round the student sees the analysis, upsolves and explains", async () => {
    let explained = false;
    mockApi({
      "GET /api/contests/4": () => ({
        id: 4,
        course_id: 2,
        title: "СПбГУ 1",
        format: "icpc",
        starts_at: "2026-01-01T10:00:00Z",
        ends_at: "2026-01-01T12:00:00Z",
        freeze_minutes: 60,
        penalty_minutes: 20,
        task_count: 2,
        state: "finished",
        task_ids: [],
        my_virtual: null,
        problems: [],
        writing: false,
      }),
      "GET /api/contests/4/standings": () => ({ format: "icpc", frozen: false, virtual: false, tasks: [], rows: [] }),
      "GET /api/contests/4/review": () => ({
        took_part: true,
        analyses: [{ id: 1, task_id: 9, title: "Станоктар", editorial_md: "Жауап бойынша екілік іздеу." }],
        upsolve: [
          { task_id: 9, label: "A", title: "Станоктар", solved_in_round: true, upsolved: false },
          { task_id: 10, label: "B", title: "Рюкзак", solved_in_round: false, upsolved: false },
        ],
        explainable: [{ submission_id: 50, task_id: 9, explained: false }],
      }),
      "POST /api/submissions/50/explain": () => {
        explained = true;
        return json(201, { submission_id: 50, status: "queued" });
      },
    });
    renderAt("/student/contests/4", "/student/contests/:contestId", <ContestPage />);
    expect(await screen.findByText("Жауап бойынша екілік іздеу.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "B. Рюкзак" })).toHaveAttribute("href", "/student/olympiad/problems/10");
    expect(screen.getByText(/қайта шешу керек/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("A. Станоктар"), "Жауапты екілік іздеумен таптым, тексеру монотонды.");
    await userEvent.click(screen.getByRole("button", { name: "Түсіндірмені жіберу" }));
    await waitFor(() => expect(explained).toBe(true));
  });
});

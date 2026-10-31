import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import i18n from "../../i18n";
import { mockApi } from "../../test/fetchMock";
import { ActivityPage } from "./ActivityPage";

beforeEach(async () => {
  await i18n.changeLanguage("kk");
});

describe("ft29 teacher activity", () => {
  it("ft29: teacher sees verdicts and large pastes per student", async () => {
    mockApi({
      "GET /api/assessments/3": () => ({
        id: 3, course_id: 1, title: "1-БЖ", starts_at: "2030-01-01T09:00:00Z",
        ends_at: "2030-01-01T11:00:00Z", genai_mode: "forbidden", task_ids: [9],
      }),
      "GET /api/assessments/3/activity": () => [
        { user_id: 5, full_name: "Айгерім", sessions: ["a", "b"], large_pastes: 2,
          pasted_chars: 1400, focus_lost: 4, last_verdicts: { "9": "WA" } },
      ],
      "GET /api/tasks?course_id=1": () => [
        { id: 9, course_id: 1, topic_id: null, external_key: null, title: "Жұп немесе тақ",
          level: "I", level_status: "confirmed", status: "approved" },
      ],
    });
    render(
      <MemoryRouter initialEntries={["/teacher/assessments/3"]}>
        <Routes>
          <Route path="/teacher/assessments/:assessmentId" element={<ActivityPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const row = (await screen.findByText("Айгерім")).closest("tr")!;
    expect(row).toHaveTextContent("WA — қате жауап");
    expect(row).toHaveTextContent("1400");
    expect(await screen.findByRole("columnheader", { name: "Жұп немесе тақ" })).toBeInTheDocument();
    expect(screen.getByText(/тек белгі, дәлел емес/)).toBeInTheDocument();
  });
});

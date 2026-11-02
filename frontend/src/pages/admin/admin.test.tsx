import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import type { User } from "../../api/client";
import i18n from "../../i18n";
import { json, mockApi } from "../../test/fetchMock";
import { AdminHomePage } from "./AdminHomePage";

const STUDENT: User = {
  id: 2,
  email: "s@example.com",
  full_name: "Айгерім",
  roles: ["student"],
  is_active: true,
  two_factor_enabled: false,
};
const TEACHER: User = {
  ...STUDENT,
  id: 3,
  email: "t@example.com",
  full_name: "Бақыт",
  roles: ["teacher"],
};

describe("admin cabinet (spec 2, 14.1)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("kk");
  });

  it("sec14: creates a user with the chosen roles", async () => {
    let sent: unknown;
    mockApi({
      "GET /api/admin/users?limit=500": () => [STUDENT],
      "POST /api/admin/users": (init) => {
        sent = JSON.parse(String(init?.body));
        return json(201, { ...TEACHER, id: 9 });
      },
    });
    render(<AdminHomePage />);
    expect(await screen.findByText("Айгерім")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Аты-жөні"), "Жаңа Оқытушы");
    await userEvent.type(
      screen.getByLabelText("Электрондық пошта"),
      "new@example.com",
    );
    await userEvent.type(
      screen.getByLabelText("Құпиясөз"),
      "long-enough-password",
    );
    const [createForm] = screen.getAllByLabelText("Оқытушы");
    await userEvent.click(createForm!);
    await userEvent.click(screen.getByRole("button", { name: "Құру" }));
    await waitFor(() =>
      expect(sent).toEqual({
        email: "new@example.com",
        full_name: "Жаңа Оқытушы",
        password: "long-enough-password",
        roles: ["student", "teacher"],
      }),
    );
    expect(await screen.findByText("Пайдаланушы қосылды.")).toBeInTheDocument();
  });

  it("sec14: blocks a user and shows the server's refusal", async () => {
    let blocked: unknown;
    mockApi({
      "GET /api/admin/users?limit=500": () => [STUDENT],
      "PUT /api/admin/users/2/active": (init) => {
        blocked = JSON.parse(String(init?.body));
        return { ...STUDENT, is_active: false };
      },
      "PUT /api/admin/users/2/roles": () =>
        json(400, { detail: "cannot_remove_own_admin" }),
    });
    render(<AdminHomePage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Басқару" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Бұғаттау" }));
    await waitFor(() => expect(blocked).toEqual({ active: false }));
    await userEvent.click(
      screen.getByRole("button", { name: "Рөлдерді сақтау" }),
    );
    expect(
      await screen.findByText("Өзіңізден әкімші рөлін ала алмайсыз."),
    ).toBeInTheDocument();
  });

  it("sec14: anonymizing asks for a second confirmation", async () => {
    let calls = 0;
    mockApi({
      "GET /api/admin/users?limit=500": () => [STUDENT],
      "POST /api/admin/users/2/anonymize": () => {
        calls += 1;
        return STUDENT;
      },
    });
    render(<AdminHomePage />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Басқару" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Анонимдеу" }));
    expect(calls).toBe(0);
    await userEvent.click(
      screen.getByRole("button", { name: "Иә, анонимдеу" }),
    );
    await waitFor(() => expect(calls).toBe(1));
  });

  it("sec14: adds a student to a group and removes a teacher", async () => {
    const posted: unknown[] = [];
    let removed = false;
    const group = {
      id: 5,
      name: "IT-21",
      students: [],
      teachers: [{ id: 3, full_name: "Бақыт" }],
    };
    mockApi({
      "GET /api/admin/users?limit=500": () => [STUDENT, TEACHER],
      "GET /api/admin/groups": () => [group],
      "GET /api/admin/users?limit=500&role=student": () => [STUDENT],
      "GET /api/admin/users?limit=500&role=teacher": () => [TEACHER],
      "POST /api/admin/groups/5/members": (init) => {
        posted.push(JSON.parse(String(init?.body)));
        return group;
      },
      "DELETE /api/admin/groups/5/teachers/3": () => {
        removed = true;
        return group;
      },
    });
    render(<AdminHomePage />);
    await userEvent.click(screen.getByRole("button", { name: "Топтар" }));
    expect(
      await screen.findByRole("heading", { name: "IT-21" }),
    ).toBeInTheDocument();
    const picker = screen.getByRole("combobox", { name: "Студентті таңдаңыз" });
    await screen.findByRole("option", { name: "Айгерім (s@example.com)" });
    await userEvent.selectOptions(picker, "2");
    const [addStudent] = screen.getAllByRole("button", { name: "Қосу" });
    await userEvent.click(addStudent!);
    await waitFor(() => expect(posted).toEqual([{ user_id: 2 }]));
    await userEvent.click(screen.getByRole("button", { name: "Өшіру" }));
    await waitFor(() => expect(removed).toBe(true));
  });

  it("sec14: filters the audit log by action", async () => {
    const row = {
      id: 1,
      created_at: "2026-11-02T10:00:00Z",
      actor_id: 1,
      action: "group_created",
      object_type: "group",
      object_id: 5,
      ip: null,
      details: {},
    };
    mockApi({
      "GET /api/admin/users?limit=500": () => [],
      "GET /api/admin/audit-log?limit=200": () => [],
      "GET /api/admin/audit-log?limit=200&action=group_created": () => [row],
    });
    render(<AdminHomePage />);
    await userEvent.click(
      screen.getByRole("button", { name: "Аудит журналы" }),
    );
    await userEvent.type(screen.getByLabelText("Әрекет"), "group_created");
    await userEvent.click(screen.getByRole("button", { name: "Іздеу" }));
    expect(await screen.findByText("group #5")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import i18n from "../i18n";

const student = {
  id: 7,
  email: "student@example.com",
  full_name: "Demo Student",
  roles: ["student"],
  is_active: true,
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockLoginResponse(response: Response) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/auth/refresh")) return json(401, { detail: "invalid_refresh_token" });
    if (url.endsWith("/api/auth/login")) return response;
    throw new Error(`unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderApp() {
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function submit(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Электрондық пошта"), email);
  await user.type(screen.getByLabelText("Құпиясөз"), password);
  await user.click(screen.getByRole("button", { name: "Кіру" }));
}

describe("sec14 login page", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("kk");
  });

  it("sec14: successful login opens the student cabinet", async () => {
    const fetchMock = mockLoginResponse(
      json(200, { access_token: "token", expires_in: 900, user: student }),
    );
    renderApp();
    await submit("student@example.com", "correct-password");
    expect(await screen.findByRole("heading", { name: "Студент кабинеті" })).toBeInTheDocument();
    const loginCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/login"));
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({
      email: "student@example.com",
      password: "correct-password",
    });
  });

  it("sec14: wrong password shows an error", async () => {
    mockLoginResponse(json(401, { detail: "invalid_credentials" }));
    renderApp();
    await submit("student@example.com", "wrong");
    expect(await screen.findByRole("alert")).toHaveTextContent("Пошта немесе құпиясөз қате.");
  });

  it("sec14: too many attempts shows the rate-limit message", async () => {
    mockLoginResponse(json(429, { detail: "too_many_attempts" }));
    renderApp();
    await submit("student@example.com", "wrong");
    expect(await screen.findByRole("alert")).toHaveTextContent("Кіру әрекеттері тым көп.");
  });
});

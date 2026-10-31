import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import i18n from "../i18n";
import { json } from "../test/fetchMock";

const student = {
  id: 7,
  email: "student@example.com",
  full_name: "Demo Student",
  roles: ["student"],
  is_active: true,
  consent_version: null as string | null,
};

type Route = (body: Record<string, unknown>) => Response;

/** Known routes answer from the table; other GETs (cabinet data) get an empty list. */
function mockApi(routes: Record<string, Route>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${new URL(String(input), "http://localhost").pathname}`;
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    if (routes[key]) return routes[key](body);
    if (key === "POST /api/auth/refresh") return json(401, { detail: "invalid_refresh_token" });
    if (key.startsWith("GET ")) return json(200, []);
    throw new Error(`unexpected request ${key}`);
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

async function signIn() {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Электрондық пошта"), "student@example.com");
  await user.type(screen.getByLabelText("Құпиясөз"), "correct-password");
  await user.click(screen.getByRole("button", { name: "Кіру" }));
  return user;
}

describe("sec14 second factor and consent", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("kk");
  });

  it("sec14: login asks for the authenticator code and sends it", async () => {
    const consented = { ...student, consent_version: "2026-1" };
    const fetchMock = mockApi({
      "POST /api/auth/login": (body) =>
        body.otp === "123456"
          ? json(200, { access_token: "t", expires_in: 900, user: consented })
          : json(401, { detail: "otp_required" }),
    });
    renderApp();
    const user = await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent("кодты енгізіңіз");
    await user.type(screen.getByLabelText(/6 таңбалы код/), "123456");
    await user.click(screen.getByRole("button", { name: "Кіру" }));
    expect(await screen.findByRole("heading", { name: "Студент кабинеті" })).toBeInTheDocument();
    const logins = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/login"));
    expect(JSON.parse(String(logins.at(-1)?.[1]?.body))).toMatchObject({ otp: "123456" });
  });

  it("sec14: a student gives consent before opening the cabinet", async () => {
    let consent: string | null = null;
    const state = () => ({
      version: "2026-1",
      accepted_version: consent,
      accepted_at: null,
      withdrawn_at: null,
    });
    mockApi({
      "POST /api/auth/login": () => json(200, { access_token: "t", expires_in: 900, user: student }),
      "GET /api/consent": () => json(200, state()),
      "POST /api/consent": (body) => {
        consent = String(body.version);
        return json(200, state());
      },
      "GET /api/me": () => json(200, { ...student, consent_version: consent }),
    });
    renderApp();
    const user = await signIn();
    expect(await screen.findByRole("heading", { name: /келісім/ })).toBeInTheDocument();
    expect(screen.getByText(/AI бағасы — алдын ала баға/)).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Келісім беру" });
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(submit);
    expect(await screen.findByRole("heading", { name: "Студент кабинеті" })).toBeInTheDocument();
    expect(consent).toBe("2026-1");
  });
});

describe("sec14 second factor setup", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("kk");
  });

  it("sec14: a teacher enables the factor with a code and password, then signs in again", async () => {
    const teacher = { ...student, roles: ["teacher"], two_factor_enabled: false };
    let enableBody: Record<string, unknown> = {};
    mockApi({
      "POST /api/auth/login": () => json(200, { access_token: "t", expires_in: 900, user: teacher }),
      "POST /api/auth/2fa/setup": () =>
        json(200, { secret: "ABCDEF234567", otpauth_uri: "otpauth://totp/x" }),
      "POST /api/auth/2fa/enable": (body) => {
        enableBody = body;
        return json(200, { ...teacher, two_factor_enabled: true });
      },
      "POST /api/auth/logout": () => new Response(null, { status: 204 }),
    });
    renderApp();
    const user = await signIn();
    await user.click(await screen.findByRole("button", { name: "Баптауды бастау" }));
    expect(await screen.findByText("ABCDEF234567")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/6 таңбалы код/), "123456");
    await user.type(screen.getByLabelText(/растау үшін/), "correct-password");
    await user.click(screen.getByRole("button", { name: "Қосу" }));
    expect(await screen.findByLabelText("Электрондық пошта")).toBeInTheDocument();
    expect(enableBody).toEqual({ code: "123456", password: "correct-password" });
  });
});

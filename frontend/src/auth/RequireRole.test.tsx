import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import type { Role, User } from "../api/client";
import i18n from "../i18n";
import { AuthContext, type AuthState, homeFor } from "./AuthContext";
import { RequireRole } from "./RequireRole";

function userWith(...roles: Role[]): User {
  return {
    id: 1,
    email: "u@example.com",
    full_name: "U",
    roles,
    is_active: true,
    two_factor_enabled: true,
    consent_version: "2026-1",
  };
}

function renderAt(path: string, user: User | null) {
  const state: AuthState = {
    user,
    loading: false,
    signIn: async () => userWith("student"),
    signOut: async () => undefined,
  };
  return render(
    <AuthContext.Provider value={state}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<p>login page</p>} />
          <Route path="/security" element={<p>security page</p>} />
          <Route path="/consent" element={<p>consent page</p>} />
          <Route
            path="/student"
            element={
              <RequireRole role="student">
                <p>student cabinet</p>
              </RequireRole>
            }
          />
          <Route
            path="/teacher"
            element={
              <RequireRole role="teacher">
                <p>teacher cabinet</p>
              </RequireRole>
            }
          />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe("sec14 second factor and consent", () => {
  it("sec14: teacher without a second factor is sent to the security page", () => {
    renderAt("/teacher", { ...userWith("teacher"), two_factor_enabled: false });
    expect(screen.getByText("security page")).toBeInTheDocument();
  });

  it("sec14: student without consent is sent to the consent page", () => {
    renderAt("/student", { ...userWith("student"), consent_version: null });
    expect(screen.getByText("consent page")).toBeInTheDocument();
  });
});

describe("sec14 role-protected routes", () => {
  it("sec14: unauthenticated user is sent to the login page", () => {
    renderAt("/teacher", null);
    expect(screen.getByText("login page")).toBeInTheDocument();
  });

  it("sec14: student cannot open the teacher cabinet", async () => {
    await i18n.changeLanguage("kk");
    renderAt("/teacher", userWith("student"));
    expect(screen.queryByText("teacher cabinet")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("рұқсатыңыз жоқ");
  });

  it("sec14: teacher opens the teacher cabinet", () => {
    renderAt("/teacher", userWith("teacher"));
    expect(screen.getByText("teacher cabinet")).toBeInTheDocument();
  });
});

describe("sec2 role home pages", () => {
  it("sec2: one role goes to its cabinet, several roles to the chooser", () => {
    expect(homeFor(userWith("coach"))).toBe("/coach");
    expect(homeFor(userWith("teacher", "coach"))).toBe("/choose-role");
  });
});

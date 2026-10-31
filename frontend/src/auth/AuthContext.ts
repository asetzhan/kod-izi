import { createContext, useContext } from "react";

import type { Role, User } from "../api/client";

export interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string, otp?: string) => Promise<User>;
  signOut: () => Promise<void>;
  /** Reload the user after a change of the second factor or consent. */
  refreshUser?: () => Promise<void>;
}

/** Spec 14.1: teachers and administrators work only with a second factor. */
export function needsSecondFactor(user: User): boolean {
  return (user.roles.includes("teacher") || user.roles.includes("admin")) && !user.two_factor_enabled;
}

/** Spec 14.3: a student works only after consenting to data processing. */
export function needsConsent(user: User): boolean {
  const staff = user.roles.some((r) => r !== "student");
  return !staff && user.roles.includes("student") && !user.consent_version;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (state === null) throw new Error("useAuth must be used inside <AuthProvider>");
  return state;
}

export const ROLE_HOME: Record<Role, string> = {
  student: "/student",
  teacher: "/teacher",
  coach: "/coach",
  admin: "/admin",
};

/** A user with one role goes straight to its cabinet; with several, to the chooser. */
export function homeFor(user: User): string {
  const [only, ...rest] = user.roles;
  return only !== undefined && rest.length === 0 ? ROLE_HOME[only] : "/choose-role";
}

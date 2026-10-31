import { createContext, useContext } from "react";

import type { Role, User } from "../api/client";

export interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => Promise<void>;
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

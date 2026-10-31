import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import * as api from "../api/client";
import { clearUserTrace, sendEvents } from "../workspace/TraceRecorder";
import { AuthContext, type AuthState } from "./AuthContext";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<api.User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Restore the session from the refresh cookie after a page reload.
    api
      .refresh()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const signIn = useCallback(async (email: string, password: string, otp?: string) => {
    const signedIn = await api.login(email, password, otp);
    setUser(signedIn);
    return signedIn;
  }, []);

  const refreshUser = useCallback(async () => {
    setUser(await api.apiGet<api.User>("/api/me"));
  }, []);

  const signOut = useCallback(async () => {
    if (user) await clearUserTrace(sendEvents, user.id);
    setUser(null);
    await api.logout();
  }, [user]);

  const value = useMemo<AuthState>(
    () => ({ user, loading, signIn, signOut, refreshUser }),
    [user, loading, signIn, signOut, refreshUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

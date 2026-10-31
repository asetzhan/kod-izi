import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router";

import type { Role } from "../api/client";
import { useAuth } from "./AuthContext";

/**
 * Hides pages from users without the role. Convenience only: the server checks
 * every request itself (spec 14.1).
 */
export function RequireRole({ role, children }: { role?: Role; children: ReactNode }) {
  const { user, loading } = useAuth();
  const { t } = useTranslation();

  if (loading) return <p>{t("common.loading")}</p>;
  if (user === null) return <Navigate to="/login" replace />;
  if (role !== undefined && !user.roles.includes(role)) {
    return <p role="alert">{t("errors.forbidden")}</p>;
  }
  return <>{children}</>;
}

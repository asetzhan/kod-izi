import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes } from "react-router";

import { ROLES } from "./api/client";
import { homeFor, ROLE_HOME, useAuth } from "./auth/AuthContext";
import { RequireRole } from "./auth/RequireRole";
import { Layout } from "./components/Layout";
import { CabinetPage } from "./pages/CabinetPage";
import { ChooseRolePage } from "./pages/ChooseRolePage";
import { LoginPage } from "./pages/LoginPage";

function RootRedirect() {
  const { user, loading } = useAuth();
  const { t } = useTranslation();
  if (loading) return <p>{t("common.loading")}</p>;
  return <Navigate to={user ? homeFor(user) : "/login"} replace />;
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/choose-role"
          element={
            <RequireRole>
              <ChooseRolePage />
            </RequireRole>
          }
        />
        {ROLES.map((role) => (
          <Route
            key={role}
            path={ROLE_HOME[role]}
            element={
              <RequireRole role={role}>
                <CabinetPage role={role} />
              </RequireRole>
            }
          />
        ))}
        <Route path="*" element={<RootRedirect />} />
      </Route>
    </Routes>
  );
}

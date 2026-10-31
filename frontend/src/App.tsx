import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes } from "react-router";

import type { ReactNode } from "react";

import { type Role, ROLES } from "./api/client";
import { homeFor, ROLE_HOME, useAuth } from "./auth/AuthContext";
import { RequireRole } from "./auth/RequireRole";
import { Layout } from "./components/Layout";
import { CabinetPage } from "./pages/CabinetPage";
import { ChooseRolePage } from "./pages/ChooseRolePage";
import { LoginPage } from "./pages/LoginPage";
import { StudentHomePage } from "./pages/student/StudentHomePage";
import { CoursePage } from "./pages/teacher/CoursePage";
import { CoursesPage } from "./pages/teacher/CoursesPage";
import { TaskEditorPage } from "./pages/teacher/TaskEditorPage";

// Roles without their own page yet keep the empty cabinet.
const HOME_PAGES: Partial<Record<Role, ReactNode>> = {
  student: <StudentHomePage />,
  teacher: <CoursesPage />,
};

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
            element={<RequireRole role={role}>{HOME_PAGES[role] ?? <CabinetPage role={role} />}</RequireRole>}
          />
        ))}
        <Route path="/teacher/courses/:courseId" element={<RequireRole role="teacher"><CoursePage /></RequireRole>} />
        <Route
          path="/teacher/courses/:courseId/tasks/new"
          element={<RequireRole role="teacher"><TaskEditorPage /></RequireRole>}
        />
        <Route path="/teacher/tasks/:taskId" element={<RequireRole role="teacher"><TaskEditorPage /></RequireRole>} />
        <Route path="*" element={<RootRedirect />} />
      </Route>
    </Routes>
  );
}

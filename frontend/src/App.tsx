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
import { AssessmentPage } from "./pages/student/AssessmentPage";
import { StudentHomePage } from "./pages/student/StudentHomePage";
import { WorkspacePage } from "./pages/student/WorkspacePage";
import { ActivityPage } from "./pages/teacher/ActivityPage";
import { MaterialsPage } from "./pages/teacher/MaterialsPage";
import { RubricPage } from "./pages/teacher/RubricPage";
import { SubmissionReviewPage } from "./pages/teacher/SubmissionReviewPage";
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
        <Route
          path="/teacher/courses/:courseId/rubric"
          element={<RequireRole role="teacher"><RubricPage /></RequireRole>}
        />
        <Route
          path="/teacher/courses/:courseId/materials"
          element={<RequireRole role="teacher"><MaterialsPage /></RequireRole>}
        />
        <Route
          path="/teacher/submissions/:submissionId"
          element={<RequireRole role="teacher"><SubmissionReviewPage /></RequireRole>}
        />
        <Route
          path="/teacher/assessments/:assessmentId"
          element={<RequireRole role="teacher"><ActivityPage /></RequireRole>}
        />
        <Route
          path="/student/assessments/:assessmentId"
          element={<RequireRole role="student"><AssessmentPage /></RequireRole>}
        />
        <Route
          path="/student/assessments/:assessmentId/tasks/:taskId"
          element={<RequireRole role="student"><WorkspacePage /></RequireRole>}
        />
        <Route path="/teacher/tasks/:taskId" element={<RequireRole role="teacher"><TaskEditorPage /></RequireRole>} />
        <Route path="*" element={<RootRedirect />} />
      </Route>
    </Routes>
  );
}

import {
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { useEffect } from "react";
import { AppShell } from "../layouts/AppShell";
import { DashboardPage } from "../pages/DashboardPage";
import { DraftReviewPage } from "../pages/DraftReviewPage";
import { DraftsPage } from "../pages/DraftsPage";
import { PublishPage } from "../pages/PublishPage";
import { QuestionDetailPage } from "../pages/QuestionDetailPage";
import { QuestionsPage } from "../pages/QuestionsPage";
import { SettingsPage } from "../pages/SettingsPage";
import { PromptsPage } from "../pages/PromptsPage";
import { BrowserSettingsPage } from "../pages/BrowserSettingsPage";
import { OpenSourcePage } from "../pages/OpenSourcePage";
import { TasksPage } from "../pages/TasksPage";

export const routeInventory = [
  "/dashboard",
  "/questions",
  "/questions/:id",
  "/tasks",
  "/drafts",
  "/drafts/:id/review",
  "/publish",
  "/settings",
  "/settings/ai",
  "/prompts",
  "/settings/browser",
  "/settings/open-source",
] as const;

function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname]);

  return null;
}

export function AppRoutes() {
  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/questions" element={<QuestionsPage />} />
          <Route path="/questions/:id" element={<QuestionDetailPage />} />
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/drafts" element={<DraftsPage />} />
          <Route path="/drafts/:id/review" element={<DraftReviewPage />} />
          <Route path="/publish" element={<PublishPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/ai" element={<SettingsPage initialSection="ai" />} />
          <Route path="/prompts" element={<PromptsPage />} />
          <Route path="/settings/browser" element={<BrowserSettingsPage />} />
          <Route path="/settings/open-source" element={<OpenSourcePage />} />
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
  );
}

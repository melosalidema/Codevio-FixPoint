import { Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { AboutPage } from "./pages/AboutPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RunConsolePage } from "./pages/RunConsolePage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsPage } from "./pages/RunsPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<RunConsolePage />} />
        <Route path="evaluation" element={<EvaluationPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
        <Route path="about" element={<AboutPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

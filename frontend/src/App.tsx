import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ToastHost } from "./lib/toast";
import { Today } from "./pages/Today";
import { Library } from "./pages/Library";
import { PaperDetail } from "./pages/PaperDetail";
import { Feed } from "./pages/Feed";
import { Ideas } from "./pages/Ideas";
import { Experiments } from "./pages/Experiments";
import { ExperimentDetail } from "./pages/ExperimentDetail";
import { Drafts } from "./pages/Drafts";
import { DraftDetail } from "./pages/DraftDetail";
import { Graph } from "./pages/Graph";
import { SettingsPage } from "./pages/Settings";
import { NotFound } from "./pages/NotFound";

export function App() {
  return (
    <>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Today />} />
          <Route path="papers" element={<Library />} />
          <Route path="papers/:id" element={<PaperDetail />} />
          <Route path="feed" element={<Feed />} />
          <Route path="ideas" element={<Ideas />} />
          <Route path="experiments" element={<Experiments />} />
          <Route path="experiments/:id" element={<ExperimentDetail />} />
          <Route path="drafts" element={<Drafts />} />
          <Route path="drafts/:id" element={<DraftDetail />} />
          <Route path="graph" element={<Graph />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
      <ToastHost />
    </>
  );
}

import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { AnalysesPage } from "./pages/AnalysesPage";
import { AnalysisDetailPage } from "./pages/AnalysisDetailPage";
import { SimulationsPage } from "./pages/SimulationsPage";
import { SimulationDetailPage } from "./pages/SimulationDetailPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/analyses" replace />} />
        <Route path="/analyses" element={<AnalysesPage />} />
        <Route path="/analyses/:id" element={<AnalysisDetailPage />} />
        <Route path="/simulations" element={<SimulationsPage />} />
        <Route path="/simulations/:runId" element={<SimulationDetailPage />} />
      </Route>
    </Routes>
  );
}

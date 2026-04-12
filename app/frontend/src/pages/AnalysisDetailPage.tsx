import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import * as Tabs from "@radix-ui/react-tabs";
import { MessageSquare } from "lucide-react";
import { api } from "../lib/api";
import type { AnalysisDetail, Matrix, SimulationTypeConfig } from "../lib/types";
import { cn } from "../lib/utils";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Spinner } from "../components/ui/spinner";
import { MatrixBuilder } from "../components/matrices/MatrixBuilder";
import { MatrixView } from "../components/matrices/MatrixView";
import { SimulationBrowser } from "../components/simulations/SimulationBrowser";
import { ThreadDrawer } from "../components/threads/ThreadDrawer";

export function AnalysisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [matrices, setMatrices] = useState<Matrix[]>([]);
  const [simTypes, setSimTypes] = useState<Record<string, SimulationTypeConfig>>({});
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const fetchAnalysis = useCallback(() => {
    if (!id) return;
    api
      .get<AnalysisDetail>(`/analyses/${id}`)
      .then(setAnalysis)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  const fetchMatrices = useCallback(() => {
    if (!id) return;
    api
      .get<{ matrices: Matrix[] }>(`/analyses/${id}/matrices`)
      .then((data) => setMatrices(data.matrices))
      .catch(console.error);
  }, [id]);

  useEffect(() => {
    fetchAnalysis();
    fetchMatrices();
    api
      .get<{ simulation_types: Record<string, SimulationTypeConfig> }>("/config/simulation-types")
      .then((data) => setSimTypes(data.simulation_types))
      .catch(console.error);
  }, [fetchAnalysis, fetchMatrices]);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!analysis) {
    return <p className="text-muted-foreground">Analysis not found.</p>;
  }

  return (
    <div className="flex h-full">
      <div className={cn("flex-1 overflow-y-auto", drawerOpen && "mr-96")}>
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-2xl font-bold">{analysis.name}</h2>
              <Badge
                variant={analysis.status === "published" ? "success" : "secondary"}
              >
                {analysis.status}
              </Badge>
            </div>
            {analysis.description && (
              <p className="text-muted-foreground mt-1">{analysis.description}</p>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Owner: {analysis.owner_email}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {analysis.status === "draft" && (
              <Button
                variant="outline"
                size="sm"
                onClick={async () => {
                  await api.post(`/analyses/${id}/publish`);
                  fetchAnalysis();
                }}
              >
                Publish
              </Button>
            )}
            <Button
              variant={drawerOpen ? "default" : "outline"}
              size="icon"
              onClick={() => setDrawerOpen(!drawerOpen)}
            >
              <MessageSquare className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <Tabs.Root defaultValue="matrices">
          <Tabs.List className="flex border-b border-border mb-6">
            {["matrices", "simulations"].map((tab) => (
              <Tabs.Trigger
                key={tab}
                value={tab}
                className="px-4 py-2 text-sm font-medium text-muted-foreground border-b-2 border-transparent data-[state=active]:text-foreground data-[state=active]:border-primary transition-colors"
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

          <Tabs.Content value="matrices">
            <MatrixBuilder
              analysisId={id!}
              simTypes={simTypes}
              onCreated={fetchMatrices}
            />
            {matrices.length === 0 ? (
              <p className="text-muted-foreground text-sm py-4">
                No matrices yet. Create one above.
              </p>
            ) : (
              matrices.map((m) => (
                <MatrixView key={m.id} matrixId={m.id} />
              ))
            )}
          </Tabs.Content>

          <Tabs.Content value="simulations">
            <SimulationBrowser
              analysisId={id!}
              linkedRunIds={analysis.simulations.map((s) => s.run_id)}
              onLink={fetchAnalysis}
            />
          </Tabs.Content>
        </Tabs.Root>
      </div>

      {/* Thread Drawer */}
      {drawerOpen && (
        <ThreadDrawer
          analysisId={id!}
          onClose={() => setDrawerOpen(false)}
        />
      )}
    </div>
  );
}

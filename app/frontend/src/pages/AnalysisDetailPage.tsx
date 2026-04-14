import { useEffect, useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import * as Tabs from "@radix-ui/react-tabs";
import { MessageSquare, Pencil, Check, X, RefreshCw } from "lucide-react";
import { ShareDialog } from "../components/analyses/ShareDialog";
import { api } from "../lib/api";
import { useUser } from "../lib/user-context";
import type { AnalysisDetail, Matrix, SimulationTypeConfig } from "../lib/types";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Spinner } from "../components/ui/spinner";
import { MatrixBuilder } from "../components/matrices/MatrixBuilder";
import { MatrixView } from "../components/matrices/MatrixView";
import { SimulationBrowser } from "../components/simulations/SimulationBrowser";
import { SimulationBuilder } from "../components/simulations/SimulationBuilder";
import { ThreadDrawer } from "../components/threads/ThreadDrawer";
import { DistributionsPanel } from "../components/distributions/DistributionsPanel";
import { GeniePanel } from "../components/distributions/GeniePanel";

export function AnalysisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useUser();
  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [matrices, setMatrices] = useState<Matrix[]>([]);
  const [simTypes, setSimTypes] = useState<Record<string, SimulationTypeConfig>>({});
  const [dashboardUrl, setDashboardUrl] = useState("");
  const [genieUrl, setGenieUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerWidth, setDrawerWidth] = useState(768); // default double-wide
  const [simRefreshKey, setSimRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  // Inline editing state
  const [editingName, setEditingName] = useState(false);
  const [editName, setEditName] = useState("");
  const [editingDesc, setEditingDesc] = useState(false);
  const [editDesc, setEditDesc] = useState("");

  const isOwner = user?.email === analysis?.owner_email;

  const fetchAnalysis = useCallback(() => {
    if (!id) return Promise.resolve();
    return api
      .get<AnalysisDetail>(`/analyses/${id}`)
      .then(setAnalysis)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  const fetchMatrices = useCallback(() => {
    if (!id) return Promise.resolve();
    return api
      .get<{ matrices: Matrix[] }>(`/analyses/${id}/matrices`)
      .then((data) => setMatrices(data.matrices))
      .catch(console.error);
  }, [id]);

  useEffect(() => {
    fetchAnalysis();
    fetchMatrices();
    api
      .get<{
        simulation_types: Record<string, SimulationTypeConfig>;
        dashboard_url?: string;
      }>("/config/simulation-types")
      .then((data: {
        simulation_types: Record<string, SimulationTypeConfig>;
        dashboard_url?: string;
        genie_url?: string;
      }) => {
        setSimTypes(data.simulation_types);
        if (data.dashboard_url) setDashboardUrl(data.dashboard_url);
        if (data.genie_url) setGenieUrl(data.genie_url);
      })
      .catch(console.error);
  }, [fetchAnalysis, fetchMatrices]);

  const handleSaveName = async () => {
    if (!editName.trim() || !id) {
      setEditingName(false);
      return;
    }
    await api.patch(`/analyses/${id}`, { name: editName.trim() });
    setAnalysis((prev) => (prev ? { ...prev, name: editName.trim() } : prev));
    setEditingName(false);
  };

  const handleSaveDesc = async () => {
    if (!id) {
      setEditingDesc(false);
      return;
    }
    const val = editDesc.trim() || null;
    await api.patch(`/analyses/${id}`, { description: val });
    setAnalysis((prev) => (prev ? { ...prev, description: val } : prev));
    setEditingDesc(false);
  };

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
      <div
        className="flex-1 overflow-y-auto transition-[margin] duration-100"
        style={{ marginRight: drawerOpen ? drawerWidth : 0 }}
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3">
              {editingName ? (
                <div className="flex items-center gap-1">
                  <Input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSaveName();
                      if (e.key === "Escape") setEditingName(false);
                    }}
                    className="h-9 text-xl font-bold w-80"
                    autoFocus
                  />
                  <Button variant="ghost" size="icon" onClick={handleSaveName}>
                    <Check className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => setEditingName(false)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <>
                  <h2 className="text-2xl font-bold">{analysis.name}</h2>
                  {isOwner && (
                    <button
                      onClick={() => {
                        setEditName(analysis.name);
                        setEditingName(true);
                      }}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                  )}
                </>
              )}
              <Badge
                variant={analysis.status === "published" ? "success" : "secondary"}
              >
                {analysis.status}
              </Badge>
            </div>

            {editingDesc ? (
              <div className="mt-2 flex gap-1 items-start">
                <textarea
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="flex-1 rounded-md border border-border bg-transparent px-3 py-2 text-sm resize-none"
                  rows={3}
                  autoFocus
                />
                <div className="flex flex-col gap-1">
                  <Button variant="ghost" size="icon" onClick={handleSaveDesc}>
                    <Check className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => setEditingDesc(false)}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-1 mt-1">
                {analysis.description ? (
                  <p className="text-muted-foreground">{analysis.description}</p>
                ) : isOwner ? (
                  <p className="text-muted-foreground/50 italic">
                    Add a description...
                  </p>
                ) : null}
                {isOwner && (
                  <button
                    onClick={() => {
                      setEditDesc(analysis.description ?? "");
                      setEditingDesc(true);
                    }}
                    className="text-muted-foreground hover:text-foreground shrink-0"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                )}
              </div>
            )}

            <p className="text-xs text-muted-foreground mt-1">
              Owner: {analysis.owner_email}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {isOwner && (
              <ShareDialog
                analysisId={analysis.id}
                isPublished={analysis.status === "published"}
                ownerEmail={analysis.owner_email}
                collaborators={analysis.collaborators}
                onUpdate={fetchAnalysis}
              />
            )}
            <Button
              variant="outline"
              size="icon"
              title="Refresh data"
              disabled={refreshing}
              onClick={async () => {
                setRefreshing(true);
                try {
                  await Promise.all([
                    fetchAnalysis(),
                    fetchMatrices(),
                  ]);
                  setSimRefreshKey((k) => k + 1);
                } finally {
                  setRefreshing(false);
                }
              }}
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            </Button>
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
        <Tabs.Root defaultValue="explore">
          <Tabs.List className="flex border-b border-border mb-6">
            {[
              { value: "explore", label: "Explore Data" },
              { value: "chat", label: "Chat with Data" },
              ...(analysis.status === "published" && !isOwner
                ? []
                : [{ value: "simulations", label: "Simulations" }]),
              { value: "matrices", label: "Matrices" },
            ].map((tab) => (
              <Tabs.Trigger
                key={tab.value}
                value={tab.value}
                className="px-4 py-2 text-sm font-medium text-muted-foreground border-b-2 border-transparent data-[state=active]:text-foreground data-[state=active]:border-primary transition-colors"
              >
                {tab.label}
              </Tabs.Trigger>
            ))}
          </Tabs.List>

          <Tabs.Content value="explore">
            <DistributionsPanel dashboardUrl={dashboardUrl} />
          </Tabs.Content>

          <Tabs.Content value="chat">
            <GeniePanel genieUrl={genieUrl} />
          </Tabs.Content>

          <Tabs.Content value="matrices">
            {isOwner && (
              <MatrixBuilder
                analysisId={id!}
                simTypes={simTypes}
                onCreated={fetchMatrices}
              />
            )}
            {matrices.length === 0 ? (
              <p className="text-muted-foreground text-sm py-4">
                {isOwner ? "No matrices yet. Create one above." : "No matrices yet."}
              </p>
            ) : (
              matrices.map((m) => (
                <MatrixView
                  key={`${m.id}-${simRefreshKey}`}
                  matrixId={m.id}
                  readOnly={!isOwner}
                  onDelete={() => setMatrices((prev) => prev.filter((x) => x.id !== m.id))}
                />
              ))
            )}
          </Tabs.Content>

          <Tabs.Content value="simulations">
            {isOwner && (
              <SimulationBuilder
                onTriggered={() => setSimRefreshKey((k) => k + 1)}
              />
            )}
            <SimulationBrowser
              key={simRefreshKey}
              analysisId={id!}
              linkedRunIds={analysis.simulations.map((s) => s.run_id)}
              onLink={fetchAnalysis}
              isOwner={isOwner}
            />
          </Tabs.Content>
        </Tabs.Root>
      </div>

      {/* Thread Drawer */}
      {drawerOpen && (
        <ThreadDrawer
          analysisId={id!}
          onClose={() => setDrawerOpen(false)}
          width={drawerWidth}
          onWidthChange={setDrawerWidth}
          onMatrixCreated={fetchMatrices}
        />
      )}
    </div>
  );
}

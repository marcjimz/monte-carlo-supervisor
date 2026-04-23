import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { LinkIcon, Search, X } from "lucide-react";
import { api } from "../../lib/api";
import type { SimulationRun } from "../../lib/types";
import { formatDate } from "../../lib/utils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Spinner } from "../ui/spinner";

interface Props {
  analysisId?: string;
  linkedRunIds?: string[];
  onLink?: () => void;
  isOwner?: boolean;
}

const SIM_TYPE_LABELS: Record<string, string> = {
  encounter_margin: "Encounter Margin Forecast",
  wh_margin_comparison: "WH Margin Comparison",
};

export function SimulationBrowser({
  analysisId,
  linkedRunIds = [],
  onLink,
  isOwner = false,
}: Props) {
  const [runs, setRuns] = useState<SimulationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [browsing, setBrowsing] = useState(false);

  // Top-level mode: no analysis context → show all runs
  const isTopLevel = !analysisId;

  const fetchRuns = useCallback(() => {
    const params = new URLSearchParams();
    if (typeFilter) params.set("simulation_type", typeFilter);
    if (statusFilter) params.set("status", statusFilter);

    return api
      .get<{ simulations: SimulationRun[] }>(
        `/simulations${params.toString() ? `?${params.toString()}` : ""}`,
      )
      .then((data) => setRuns(data.simulations));
  }, [typeFilter, statusFilter]);

  useEffect(() => {
    fetchRuns()
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [fetchRuns]);

  // Auto-poll every 15s while any run is non-terminal (SUBMITTED or RUNNING)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    const hasActive = runs.some(
      (r) => r.status === "SUBMITTED" || r.status === "RUNNING",
    );
    if (hasActive) {
      intervalRef.current = setInterval(() => {
        fetchRuns().catch(console.error);
      }, 15_000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [runs, fetchRuns]);

  const handleLink = async (runId: string) => {
    if (!analysisId) return;
    await api.post(`/analyses/${analysisId}/simulations`, { run_id: runId });
    onLink?.();
  };

  const statusBadge = (status: string) => {
    switch (status) {
      case "COMPLETED":
        return <Badge variant="success">Completed</Badge>;
      case "RUNNING":
        return <Badge variant="warning">Running</Badge>;
      case "SUBMITTED":
        return <Badge variant="secondary">Submitted</Badge>;
      case "FAILED":
        return <Badge variant="destructive">Failed</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  // Determine which runs to display
  const linkedRuns = runs.filter((r) => linkedRunIds.includes(r.run_id));
  const displayRuns = isTopLevel ? runs : browsing ? runs : linkedRuns;

  const renderTable = (rows: SimulationRun[], showActions: boolean) => (
    <div className="border border-border rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted">
            <th className="text-left p-3 font-medium">Run ID</th>
            <th className="text-left p-3 font-medium">Type</th>
            <th className="text-left p-3 font-medium">Status</th>
            <th className="text-left p-3 font-medium">Trials</th>
            <th className="text-left p-3 font-medium">Created</th>
            {showActions && analysisId && (
              <th className="text-right p-3 font-medium">Actions</th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((run) => (
            <tr key={run.run_id} className="border-t border-border hover:bg-muted/50">
              <td className="p-3">
                <Link
                  to={`/simulations/${run.run_id}`}
                  className="text-primary hover:underline font-mono text-xs break-all"
                >
                  {run.run_id}
                </Link>
              </td>
              <td className="p-3">{SIM_TYPE_LABELS[run.simulation_type] ?? run.simulation_type}</td>
              <td className="p-3">{statusBadge(run.status)}</td>
              <td className="p-3">{run.num_simulations.toLocaleString()}</td>
              <td className="p-3 text-muted-foreground">
                {formatDate(run.created_at)}
              </td>
              {showActions && analysisId && (
                <td className="p-3 text-right">
                  {linkedRunIds.includes(run.run_id) ? (
                    <span className="text-xs text-muted-foreground">Linked</span>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleLink(run.run_id)}
                    >
                      <LinkIcon className="h-3 w-3 mr-1" />
                      Link
                    </Button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner className="h-5 w-5" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-muted-foreground">
          {isTopLevel
            ? `All Simulations (${runs.length})`
            : browsing
              ? `All Simulations (${runs.length})`
              : `Linked Simulations (${linkedRuns.length})`}
        </h3>
        {!isTopLevel && isOwner && (
          <Button
            variant={browsing ? "default" : "outline"}
            size="sm"
            onClick={() => setBrowsing(!browsing)}
          >
            {browsing ? (
              <>
                <X className="h-3 w-3 mr-1" />
                Close Browser
              </>
            ) : (
              <>
                <Search className="h-3 w-3 mr-1" />
                Browse & Link
              </>
            )}
          </Button>
        )}
      </div>

      {/* Filters — shown on top-level page or when browsing inside an analysis */}
      {(isTopLevel || browsing) && (
        <div className="flex gap-3 mb-4">
          <select
            className="h-9 rounded-md border border-border bg-transparent px-3 text-sm"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All types</option>
            <option value="encounter_margin">Encounter Margin</option>
            <option value="wh_margin_comparison">WH Margin</option>
          </select>
          <select
            className="h-9 rounded-md border border-border bg-transparent px-3 text-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="SUBMITTED">Submitted</option>
            <option value="COMPLETED">Completed</option>
            <option value="RUNNING">Running</option>
            <option value="FAILED">Failed</option>
          </select>
        </div>
      )}

      {displayRuns.length === 0 ? (
        <p className="text-muted-foreground text-sm py-8 text-center">
          {isTopLevel
            ? "No simulations found."
            : browsing
              ? "No simulations found."
              : "No simulations linked to this analysis yet."}
        </p>
      ) : (
        renderTable(displayRuns, browsing || isOwner)
      )}
    </div>
  );
}

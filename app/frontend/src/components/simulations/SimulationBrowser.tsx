import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { LinkIcon } from "lucide-react";
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
}

export function SimulationBrowser({ analysisId, linkedRunIds = [], onLink }: Props) {
  const [runs, setRuns] = useState<SimulationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    const params = new URLSearchParams();
    if (typeFilter) params.set("simulation_type", typeFilter);
    if (statusFilter) params.set("status", statusFilter);

    api
      .get<{ simulations: SimulationRun[] }>(
        `/simulations${params.toString() ? `?${params.toString()}` : ""}`,
      )
      .then((data) => setRuns(data.simulations))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [typeFilter, statusFilter]);

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
      case "FAILED":
        return <Badge variant="destructive">Failed</Badge>;
      default:
        return <Badge variant="secondary">{status}</Badge>;
    }
  };

  return (
    <div>
      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <select
          className="h-9 rounded-md border border-border bg-transparent px-3 text-sm"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">All types</option>
          <option value="patient_volume">Patient Volume</option>
          <option value="revenue">Revenue</option>
          <option value="cost_comparison">Cost Comparison</option>
          <option value="system_cost_roi">System Cost ROI</option>
        </select>
        <select
          className="h-9 rounded-md border border-border bg-transparent px-3 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="COMPLETED">Completed</option>
          <option value="RUNNING">Running</option>
          <option value="FAILED">Failed</option>
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <Spinner className="h-5 w-5" />
        </div>
      ) : runs.length === 0 ? (
        <p className="text-muted-foreground text-sm py-8 text-center">
          No simulations found.
        </p>
      ) : (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-muted">
                <th className="text-left p-3 font-medium">Run ID</th>
                <th className="text-left p-3 font-medium">Type</th>
                <th className="text-left p-3 font-medium">Status</th>
                <th className="text-left p-3 font-medium">Trials</th>
                <th className="text-left p-3 font-medium">Created</th>
                {analysisId && (
                  <th className="text-right p-3 font-medium">Actions</th>
                )}
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id} className="border-t border-border hover:bg-muted/50">
                  <td className="p-3">
                    <Link
                      to={`/simulations/${run.run_id}`}
                      className="text-primary hover:underline font-mono text-xs"
                    >
                      {run.run_id.slice(0, 8)}...
                    </Link>
                  </td>
                  <td className="p-3">{run.simulation_type}</td>
                  <td className="p-3">{statusBadge(run.status)}</td>
                  <td className="p-3">{run.num_simulations.toLocaleString()}</td>
                  <td className="p-3 text-muted-foreground">
                    {formatDate(run.created_at)}
                  </td>
                  {analysisId && (
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
      )}
    </div>
  );
}

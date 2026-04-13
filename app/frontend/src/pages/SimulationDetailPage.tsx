import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { ArrowLeft } from "lucide-react";
import { api } from "../lib/api";
import type { SimulationDetail, SimulationResult, SimulationTypeConfig } from "../lib/types";
import { formatNumber } from "../lib/utils";
import { Badge } from "../components/ui/badge";
import { Card, CardTitle } from "../components/ui/card";
import { Spinner } from "../components/ui/spinner";

const DIST_NAME_LABELS: Record<string, string> = {
  encounter_volume: "Volume",
  gross_charges: "Gross Charges",
  denial_rate: "Denial Rate",
  inperson_cost: "In-Person Cost",
  virtual_cost: "Virtual Cost",
  baseline_cost: "Baseline Cost",
  reduction_noise: "Reduction Noise",
};

const DIST_TYPE_LABELS: Record<string, string> = {
  normal: "Normal",
  lognormal: "Log-Normal",
  beta: "Beta",
  gamma: "Gamma",
  uniform: "Uniform",
};

const PARAM_LABELS: Record<string, Record<string, string>> = {
  normal: { loc: "Mean", scale: "Std Dev" },
  lognormal: { mean: "Log Mean", sigma: "Log Std Dev" },
  beta: { a: "\u03b1", b: "\u03b2" },
  gamma: { shape: "k", scale: "\u03b8" },
  uniform: { low: "Min", high: "Max" },
};

export function SimulationDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [sim, setSim] = useState<SimulationDetail | null>(null);
  const [simTypes, setSimTypes] = useState<Record<string, SimulationTypeConfig>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    api
      .get<SimulationDetail>(`/simulations/${runId}`)
      .then(setSim)
      .catch(console.error)
      .finally(() => setLoading(false));
    api
      .get<{ simulation_types: Record<string, SimulationTypeConfig> }>("/config/simulation-types")
      .then((data) => setSimTypes(data.simulation_types))
      .catch(console.error);
  }, [runId]);

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!sim) {
    return <p className="text-muted-foreground">Simulation not found.</p>;
  }

  // Parse parameters
  let params: Record<string, unknown> = {};
  let distOverrides: Record<string, { type: string; params: Record<string, number> }> = {};
  try {
    const parsed = JSON.parse(sim.parameters);
    distOverrides = parsed.distribution_overrides ?? {};
    // Remove distribution_overrides from display params
    const { distribution_overrides: _, ...rest } = parsed;
    params = rest;
  } catch {
    // ignore
  }

  // Build distribution display: config defaults merged with any overrides
  const typeConfig = simTypes[sim.simulation_type];
  const distributions: Array<{
    name: string;
    label: string;
    type: string;
    params: Record<string, number>;
    overridden: boolean;
  }> = [];
  if (typeConfig) {
    for (const [name, def] of Object.entries(typeConfig.distributions)) {
      const override = distOverrides[name];
      distributions.push({
        name,
        label: DIST_NAME_LABELS[name] ?? name,
        type: override?.type ?? def.default_spec.type,
        params: override?.params ?? def.default_spec.params,
        overridden: !!override,
      });
    }
  }

  // Group results by metric
  const metricGroups = new Map<string, SimulationResult[]>();
  for (const r of sim.results) {
    const key = r.metric_name;
    if (!metricGroups.has(key)) metricGroups.set(key, []);
    metricGroups.get(key)!.push(r);
  }

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
      <Link
        to="/simulations"
        className="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1 mb-4"
      >
        <ArrowLeft className="h-3 w-3" /> Back to simulations
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">{sim.simulation_type}</h2>
          <p className="text-muted-foreground font-mono text-xs mt-1">
            Run ID: {sim.run_id}
          </p>
        </div>
        {statusBadge(sim.status)}
      </div>

      {/* Params */}
      <Card className="mb-6">
        <CardTitle className="text-sm mb-3">Parameters</CardTitle>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <p className="text-xs text-muted-foreground">Trials</p>
            <p className="font-mono text-sm">{sim.num_simulations.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Seed</p>
            <p className="font-mono text-sm">{sim.seed}</p>
          </div>
          {Object.entries(params).map(([key, val]) => (
            <div key={key}>
              <p className="text-xs text-muted-foreground">{key}</p>
              <p className="font-mono text-sm">{String(val)}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* Distributions */}
      {distributions.length > 0 && (
        <Card className="mb-6">
          <CardTitle className="text-sm mb-3">Distributions</CardTitle>
          <div className="grid gap-2 md:grid-cols-2">
            {distributions.map((d) => (
              <div
                key={d.name}
                className="border border-border rounded-md px-3 py-2 bg-muted/30"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium">{d.label}</span>
                  <Badge variant="secondary">{DIST_TYPE_LABELS[d.type] ?? d.type}</Badge>
                  {d.overridden && (
                    <Badge variant="warning">Custom</Badge>
                  )}
                </div>
                <p className="text-[10px] text-muted-foreground font-mono mt-1">
                  {Object.entries(d.params)
                    .map(([k, v]) => `${PARAM_LABELS[d.type]?.[k] ?? k}=${v}`)
                    .join(", ")}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Results by metric */}
      {Array.from(metricGroups.entries()).map(([metric, results]) => (
        <Card key={metric} className="mb-6">
          <CardTitle className="text-sm mb-3">{metric}</CardTitle>

          {/* Table */}
          <div className="border border-border rounded-lg overflow-hidden mb-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted">
                  <th className="text-left p-2 font-medium">{results[0]?.group_key}</th>
                  <th className="text-right p-2 font-medium">Mean</th>
                  <th className="text-right p-2 font-medium">P05</th>
                  <th className="text-right p-2 font-medium">P50</th>
                  <th className="text-right p-2 font-medium">P95</th>
                  <th className="text-right p-2 font-medium">Std</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className="border-t border-border">
                    <td className="p-2 font-medium">{r.group_value}</td>
                    <td className="p-2 text-right font-mono">
                      {formatNumber(r.mean_value)}
                    </td>
                    <td className="p-2 text-right font-mono">
                      {r.p05 != null ? formatNumber(r.p05) : "-"}
                    </td>
                    <td className="p-2 text-right font-mono">
                      {r.p50 != null ? formatNumber(r.p50) : "-"}
                    </td>
                    <td className="p-2 text-right font-mono">
                      {r.p95 != null ? formatNumber(r.p95) : "-"}
                    </td>
                    <td className="p-2 text-right font-mono text-muted-foreground">
                      {r.std_value != null ? formatNumber(r.std_value) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Chart */}
          <ResponsiveContainer width="100%" height={250}>
            <BarChart
              data={results.map((r) => ({
                name: r.group_value,
                mean: r.mean_value,
                p05: r.p05,
                p95: r.p95,
              }))}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Bar dataKey="mean" fill="#110057" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      ))}

      {sim.results.length === 0 && (
        <Card className="text-center py-8">
          <p className="text-muted-foreground text-sm">
            {sim.status === "COMPLETED"
              ? "No results available."
              : "Results will appear when the simulation completes."}
          </p>
        </Card>
      )}
    </div>
  );
}

import { useEffect, useState, useCallback, useMemo } from "react";
import { ArrowUpDown, Check, Minus, Pencil, Play, Trash2, X } from "lucide-react";
import { api } from "../../lib/api";
import type { Matrix, MatrixCell } from "../../lib/types";
import { formatNumber } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Card, CardTitle } from "../ui/card";
import { Spinner } from "../ui/spinner";
import { Badge } from "../ui/badge";

interface Props {
  matrixId: string;
  readOnly?: boolean;
  onDelete?: () => void;
}

const SIM_TYPE_LABELS: Record<string, string> = {
  encounter_margin: "Encounter Margin Forecast",
  wh_margin_comparison: "WH Margin Comparison",
};

/** Format a parameter name to human-readable label. */
function formatParamName(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Format a cell value smartly — percentages, large numbers, etc. */
function formatCellValue(param: string, value: number): string {
  if (
    (param.includes("penetration") ||
      param.includes("rate") ||
      param.includes("ratio") ||
      param.includes("percent") ||
      param.includes("pct") ||
      param.includes("fraction")) &&
    value > 0 &&
    value <= 1
  ) {
    return `${(value * 100).toFixed(0)}%`;
  }
  if (param.includes("cost") || param.includes("savings") || param.includes("revenue") || param.includes("charge") || param.includes("margin")) {
    if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(0)}M`;
    if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
    return `$${formatNumber(value, 0)}`;
  }
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
  if (value % 1 !== 0) return formatNumber(value, 2);
  return formatNumber(value, 0);
}

/** Detect how to format a metric based on its name. */
type MetricFormat = "currency" | "ratio" | "count";

function detectMetricFormat(metricName: string): MetricFormat {
  const lower = metricName.toLowerCase();
  if (lower.includes("roi") || lower.includes("_rate") || lower.includes("_ratio") || lower.includes("_pct"))
    return "ratio";
  if (lower.includes("encounter") || lower.includes("volume") || lower.includes("count"))
    return "count";
  return "currency";
}

/** Format a result value based on metric type. */
function formatResultValue(value: number, format: MetricFormat = "currency"): string {
  switch (format) {
    case "ratio":
      return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
    case "count":
      if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
      if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
      return formatNumber(value, 0);
    default:
      if (Math.abs(value) >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`;
      if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
      if (Math.abs(value) >= 10_000) return `$${(value / 1_000).toFixed(0)}K`;
      return `$${formatNumber(value, 0)}`;
  }
}

/** Compute heatmap opacity for a normalized 0-1 value. */
function heatmapOpacity(normalized: number): number {
  return 0.03 + normalized * 0.42;
}

export function MatrixView({ matrixId, readOnly = false, onDelete }: Props) {
  const [matrix, setMatrix] = useState<Matrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);
  const [reversed, setReversed] = useState(false);

  // Inline editing state
  const [editingName, setEditingName] = useState(false);
  const [editName, setEditName] = useState("");
  const [editingDesc, setEditingDesc] = useState(false);
  const [editDesc, setEditDesc] = useState("");
  const [runningAll, setRunningAll] = useState(false);
  const [runError, setRunError] = useState("");

  const fetchMatrix = useCallback(() => {
    api
      .get<Matrix>(`/matrices/${matrixId}`)
      .then(setMatrix)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [matrixId]);

  useEffect(() => {
    fetchMatrix();
  }, [fetchMatrix]);

  // Auto-poll when there are running cells
  useEffect(() => {
    if (!matrix) return;
    const hasIncomplete = matrix.cells.some(
      (c) => c.status === "running" || c.status === "queued" || c.status === "pending",
    );
    if (!hasIncomplete) return;

    const interval = setInterval(async () => {
      setPolling(true);
      try {
        const updated = await api.get<Matrix>(`/matrices/${matrixId}/status`);
        setMatrix(updated);
      } catch {
        // ignore
      }
      setPolling(false);
    }, 10_000);

    return () => clearInterval(interval);
  }, [matrix, matrixId]);

  // Compute heatmap min/max from completed cells
  const { minMean, maxMean } = useMemo(() => {
    if (!matrix) return { minMean: 0, maxMean: 0 };
    const completedMeans = matrix.cells
      .filter((c) => c.status === "completed" && c.result_mean != null)
      .map((c) => c.result_mean!);
    if (completedMeans.length === 0) return { minMean: 0, maxMean: 0 };
    return {
      minMean: Math.min(...completedMeans),
      maxMean: Math.max(...completedMeans),
    };
  }, [matrix]);

  if (loading || !matrix) {
    return <Spinner className="h-5 w-5" />;
  }

  // Build 2D grid lookup
  const cellMap = new Map<string, MatrixCell>();
  for (const cell of matrix.cells) {
    cellMap.set(`${cell.row_value}|${cell.col_value}`, cell);
  }

  const completedCount = matrix.cells.filter((c) => c.status === "completed").length;
  const runningCount = matrix.cells.filter((c) => c.status === "running" || c.status === "queued").length;
  const pendingCount = matrix.cells.filter((c) => c.status === "pending").length;
  const failedCount = matrix.cells.filter((c) => c.status === "failed").length;
  const totalCells = matrix.row_values.length * matrix.col_values.length;

  const handleRunAll = async () => {
    setRunningAll(true);
    setRunError("");
    try {
      await api.post(`/matrices/${matrixId}/run`);
      fetchMatrix();
    } catch (err) {
      console.error("Run all failed:", err);
      setRunError(err instanceof Error ? err.message : "Failed to trigger runs");
      fetchMatrix(); // still refresh — some cells may have been triggered
    } finally {
      setRunningAll(false);
    }
  };

  const handleRunCell = async (cellId: string) => {
    setRunError("");
    try {
      await api.post(`/matrices/${matrixId}/cells/${cellId}/run`);
      fetchMatrix();
    } catch (err) {
      console.error("Run cell failed:", err);
      setRunError(err instanceof Error ? err.message : "Failed to trigger cell");
      fetchMatrix();
    }
  };

  const rowLabel = formatParamName(matrix.row_parameter);
  const colLabel = formatParamName(matrix.col_parameter);
  const simTypeLabel = SIM_TYPE_LABELS[matrix.simulation_type] ?? matrix.simulation_type;
  const outputLabel = formatParamName(matrix.output_metric);
  const metricFormat = detectMetricFormat(matrix.output_metric);

  const handleSaveName = async () => {
    if (!editName.trim()) {
      setEditingName(false);
      return;
    }
    await api.patch(`/matrices/${matrixId}`, { name: editName.trim() });
    setMatrix((prev) => (prev ? { ...prev, name: editName.trim() } : prev));
    setEditingName(false);
  };

  const handleSaveDesc = async () => {
    const val = editDesc.trim() || null;
    await api.patch(`/matrices/${matrixId}`, { description: val });
    setMatrix((prev) => (prev ? { ...prev, description: val } : prev));
    setEditingDesc(false);
  };

  /** Get heatmap background + text style for a cell's mean value. */
  const getCellStyle = (mean: number | null): React.CSSProperties => {
    if (mean == null || maxMean === minMean) return {};
    const range = maxMean - minMean;
    let normalized = (mean - minMean) / range;
    if (reversed) normalized = 1 - normalized;
    const opacity = heatmapOpacity(normalized);
    return {
      backgroundColor: `rgba(17, 0, 87, ${opacity})`,
      ...(opacity > 0.3 ? { color: "#fff" } : {}),
    };
  };

  // Status summary parts
  const statusParts: string[] = [];
  if (completedCount > 0) statusParts.push(`${completedCount} completed`);
  if (runningCount > 0) statusParts.push(`${runningCount} running`);
  if (pendingCount > 0) statusParts.push(`${pendingCount} pending`);
  if (failedCount > 0) statusParts.push(`${failedCount} failed`);

  const runnableCount = pendingCount + failedCount;

  return (
    <Card className="mb-4 overflow-x-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {editingName ? (
              <div className="flex items-center gap-1">
                <Input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveName();
                    if (e.key === "Escape") setEditingName(false);
                  }}
                  className="h-7 text-base font-bold w-64"
                  autoFocus
                />
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleSaveName}>
                  <Check className="h-3.5 w-3.5" />
                </Button>
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditingName(false)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ) : (
              <>
                <CardTitle className="text-base">{matrix.name}</CardTitle>
                {!readOnly && (
                  <button
                    onClick={() => {
                      setEditName(matrix.name);
                      setEditingName(true);
                    }}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <Pencil className="h-3 w-3" />
                  </button>
                )}
              </>
            )}
            <Badge variant="secondary">{simTypeLabel}</Badge>
          </div>

          {/* Description */}
          {editingDesc ? (
            <div className="mt-1 flex gap-1 items-center">
              <Input
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveDesc();
                  if (e.key === "Escape") setEditingDesc(false);
                }}
                placeholder="Add a description..."
                className="h-6 text-xs w-80"
                autoFocus
              />
              <Button variant="ghost" size="icon" className="h-5 w-5" onClick={handleSaveDesc}>
                <Check className="h-3 w-3" />
              </Button>
              <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => setEditingDesc(false)}>
                <X className="h-3 w-3" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-1 mt-1">
              {matrix.description ? (
                <p className="text-xs text-muted-foreground">{matrix.description}</p>
              ) : !readOnly ? (
                <p className="text-xs text-muted-foreground/50 italic">Add description...</p>
              ) : null}
              {!readOnly && (
                <button
                  onClick={() => {
                    setEditDesc(matrix.description ?? "");
                    setEditingDesc(true);
                  }}
                  className="text-muted-foreground hover:text-foreground shrink-0"
                >
                  <Pencil className="h-2.5 w-2.5" />
                </button>
              )}
            </div>
          )}

          <p className="text-xs text-muted-foreground mt-1">{outputLabel}</p>
          <div className="flex items-center gap-2 mt-1">
            {polling && <Spinner className="h-3 w-3" />}
            <span className="text-xs text-muted-foreground">
              {statusParts.join(", ")} of {totalCells}
            </span>
          </div>
        </div>
          <div className="flex items-center gap-2 shrink-0">
          {!readOnly && runnableCount > 0 && (
            <Button size="sm" onClick={handleRunAll} disabled={runningAll}>
              {runningAll ? (
                <>
                  <Spinner className="h-3 w-3 mr-1" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="h-3 w-3 mr-1" />
                  Run All ({runnableCount})
                </>
              )}
            </Button>
          )}
          {!readOnly && onDelete && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-destructive"
              onClick={() => {
                if (window.confirm("Delete this matrix? This cannot be undone.")) {
                  api.delete(`/matrices/${matrixId}`).then(onDelete).catch(console.error);
                }
              }}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      {/* Matrix table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-muted">
              <th className="p-2 text-left">
                <div className="text-[10px] text-muted-foreground leading-tight">
                  {rowLabel} <span className="opacity-50">&#8595;</span>
                </div>
                <div className="text-[10px] text-muted-foreground leading-tight">
                  {colLabel} <span className="opacity-50">&#8594;</span>
                </div>
              </th>
              {matrix.col_values.map((cv) => (
                <th
                  key={cv}
                  className="p-2 text-center text-xs font-semibold"
                >
                  {formatCellValue(matrix.col_parameter, cv)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.row_values.map((rv) => (
              <tr key={rv} className="border-t border-border">
                <td className="p-2 text-xs font-semibold bg-muted/50">
                  {formatCellValue(matrix.row_parameter, rv)}
                </td>
                {matrix.col_values.map((cv) => {
                  const cell = cellMap.get(`${rv}|${cv}`);
                  return (
                    <td
                      key={cv}
                      className="p-2 text-center"
                      style={cell?.status === "completed" ? getCellStyle(cell.result_mean) : {}}
                    >
                      <CellDisplay
                        cell={cell}
                        onRun={handleRunCell}
                        readOnly={readOnly}
                        metricFormat={metricFormat}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Error display */}
      {runError && (
        <p className="mt-2 text-sm text-destructive bg-destructive/10 rounded px-3 py-2">
          {runError}
        </p>
      )}

      {/* Legend footer */}
      <div className="mt-3 space-y-1.5">
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <span>Metric: {outputLabel} (mean)</span>
          <span className="text-muted-foreground/40">|</span>
          <span>{matrix.num_simulations.toLocaleString()} trials/cell</span>
          <span className="text-muted-foreground/40">|</span>
          <span>Seed: {matrix.seed}</span>
        </div>
        <div className="flex items-center gap-3">
          {/* Gradient bar */}
          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <span>{reversed ? "High" : "Low"}</span>
            <div
              className="h-2.5 w-24 rounded-sm"
              style={{
                background: `linear-gradient(to right, rgba(17,0,87,0.03), rgba(17,0,87,0.45))`,
              }}
            />
            <span>{reversed ? "Low" : "High"}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-[10px] text-muted-foreground"
            onClick={() => setReversed(!reversed)}
          >
            <ArrowUpDown className="h-3 w-3 mr-1" />
            Reverse
          </Button>
        </div>
      </div>
    </Card>
  );
}

function CellDisplay({
  cell,
  onRun,
  readOnly,
  metricFormat,
}: {
  cell: MatrixCell | undefined;
  onRun: (cellId: string) => void;
  readOnly: boolean;
  metricFormat: MetricFormat;
}) {
  if (!cell) return <Minus className="h-4 w-4 text-muted-foreground mx-auto" />;

  switch (cell.status) {
    case "completed":
      return (
        <div className="flex flex-col items-center leading-tight">
          {cell.result_p05 != null && (
            <span className="text-[10px] opacity-70 font-mono">
              P5 {formatResultValue(cell.result_p05, metricFormat)}
            </span>
          )}
          <span className="text-sm font-mono font-bold">
            {cell.result_mean != null ? formatResultValue(cell.result_mean, metricFormat) : "---"}
          </span>
          {cell.result_p95 != null && (
            <span className="text-[10px] opacity-70 font-mono">
              P95 {formatResultValue(cell.result_p95, metricFormat)}
            </span>
          )}
        </div>
      );
    case "running":
    case "queued":
      return <Spinner className="mx-auto h-4 w-4" />;
    case "failed":
      return readOnly ? (
        <span className="text-destructive text-xs">Failed</span>
      ) : (
        <button
          onClick={() => onRun(cell.id)}
          className="text-destructive text-xs hover:underline"
        >
          Failed (retry)
        </button>
      );
    default:
      return readOnly ? (
        <span className="text-muted-foreground text-xs">Pending</span>
      ) : (
        <button
          onClick={() => onRun(cell.id)}
          className="text-primary text-xs hover:underline"
        >
          Run
        </button>
      );
  }
}

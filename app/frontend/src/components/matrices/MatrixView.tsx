import { useEffect, useState, useCallback } from "react";
import { Minus, Play } from "lucide-react";
import { api } from "../../lib/api";
import type { Matrix, MatrixCell } from "../../lib/types";
import { formatNumber } from "../../lib/utils";
import { Button } from "../ui/button";
import { Card, CardTitle } from "../ui/card";
import { Spinner } from "../ui/spinner";

interface Props {
  matrixId: string;
}

export function MatrixView({ matrixId }: Props) {
  const [matrix, setMatrix] = useState<Matrix | null>(null);
  const [loading, setLoading] = useState(true);
  const [polling, setPolling] = useState(false);

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
    const hasRunning = matrix.cells.some(
      (c) => c.status === "running" || c.status === "queued",
    );
    if (!hasRunning) return;

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

  if (loading || !matrix) {
    return <Spinner className="h-5 w-5" />;
  }

  // Build 2D grid lookup
  const cellMap = new Map<string, MatrixCell>();
  for (const cell of matrix.cells) {
    cellMap.set(`${cell.row_value}|${cell.col_value}`, cell);
  }

  const pendingCount = matrix.cells.filter(
    (c) => c.status === "pending" || c.status === "failed",
  ).length;

  const handleRunAll = async () => {
    await api.post(`/matrices/${matrixId}/run`);
    fetchMatrix();
  };

  const handleRunCell = async (cellId: string) => {
    await api.post(`/matrices/${matrixId}/cells/${cellId}/run`);
    fetchMatrix();
  };

  return (
    <Card className="mb-4 overflow-x-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <CardTitle className="text-base">{matrix.name}</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            {matrix.simulation_type} &middot; {matrix.row_parameter} vs{" "}
            {matrix.col_parameter} &middot; {matrix.output_metric}
            {polling && <Spinner className="inline ml-2 h-3 w-3" />}
          </p>
        </div>
        {pendingCount > 0 && (
          <Button size="sm" onClick={handleRunAll}>
            <Play className="h-3 w-3" />
            Run All Missing ({pendingCount})
          </Button>
        )}
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr>
            <th className="text-left p-2 text-xs text-muted-foreground">
              {matrix.row_parameter} \ {matrix.col_parameter}
            </th>
            {matrix.col_values.map((cv) => (
              <th key={cv} className="p-2 text-center text-xs font-medium">
                {formatNumber(cv, cv % 1 === 0 ? 0 : 2)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.row_values.map((rv) => (
            <tr key={rv} className="border-t border-border">
              <td className="p-2 text-xs font-medium text-muted-foreground">
                {formatNumber(rv, rv % 1 === 0 ? 0 : 2)}
              </td>
              {matrix.col_values.map((cv) => {
                const cell = cellMap.get(`${rv}|${cv}`);
                return (
                  <td key={cv} className="p-2 text-center">
                    <CellDisplay cell={cell} onRun={handleRunCell} />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function CellDisplay({
  cell,
  onRun,
}: {
  cell: MatrixCell | undefined;
  onRun: (cellId: string) => void;
}) {
  if (!cell) return <Minus className="h-4 w-4 text-muted-foreground mx-auto" />;

  switch (cell.status) {
    case "completed":
      return (
        <span className="text-sm font-mono font-medium">
          {cell.result_mean != null ? formatNumber(cell.result_mean, 0) : "---"}
        </span>
      );
    case "running":
    case "queued":
      return <Spinner className="mx-auto h-4 w-4" />;
    case "failed":
      return (
        <button
          onClick={() => onRun(cell.id)}
          className="text-destructive text-xs hover:underline"
        >
          Failed (retry)
        </button>
      );
    default:
      return (
        <button
          onClick={() => onRun(cell.id)}
          className="text-primary text-xs hover:underline"
        >
          Run
        </button>
      );
  }
}

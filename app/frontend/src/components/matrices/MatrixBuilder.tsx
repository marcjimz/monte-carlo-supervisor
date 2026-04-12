import { useState } from "react";
import { api } from "../../lib/api";
import type { Matrix, SimulationTypeConfig } from "../../lib/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Card, CardTitle } from "../ui/card";

interface Props {
  analysisId: string;
  simTypes: Record<string, SimulationTypeConfig>;
  onCreated: () => void;
}

export function MatrixBuilder({ analysisId, simTypes, onCreated }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [simType, setSimType] = useState("");
  const [rowParam, setRowParam] = useState("");
  const [rowStart, setRowStart] = useState("");
  const [rowEnd, setRowEnd] = useState("");
  const [rowStep, setRowStep] = useState("");
  const [colParam, setColParam] = useState("");
  const [colValues, setColValues] = useState("");
  const [outputMetric, setOutputMetric] = useState("");
  const [groupKey, setGroupKey] = useState("");
  const [groupValue, setGroupValue] = useState("");
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const typeConfig = simType ? simTypes[simType] : null;
  const params = typeConfig ? Object.keys(typeConfig.parameters) : [];
  const metrics = typeConfig
    ? [
        typeConfig.aggregation.value_column,
        ...(typeConfig.aggregation.additional_metrics?.map((m) => m.value_column) ?? []),
      ]
    : [];

  const handleCreate = async () => {
    setSubmitting(true);
    try {
      // Build row values from start/end/step
      const rowVals: number[] = [];
      const start = parseFloat(rowStart);
      const end = parseFloat(rowEnd);
      const step = parseFloat(rowStep);
      if (!isNaN(start) && !isNaN(end) && !isNaN(step) && step > 0) {
        for (let v = start; v <= end + step / 100; v += step) {
          rowVals.push(Math.round(v * 1e10) / 1e10);
        }
      }

      // Parse col values (comma-separated)
      const cVals = colValues
        .split(",")
        .map((v) => parseFloat(v.trim()))
        .filter((v) => !isNaN(v));

      await api.post<Matrix>(`/analyses/${analysisId}/matrices`, {
        name: name || "Untitled Matrix",
        simulation_type: simType,
        row_parameter: rowParam,
        row_values: rowVals,
        col_parameter: colParam,
        col_values: cVals,
        base_parameters: {},
        output_metric: outputMetric,
        output_group_key: groupKey || null,
        output_group_value: groupValue || null,
      });

      setExpanded(false);
      onCreated();
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  if (!expanded) {
    return (
      <Button variant="outline" onClick={() => setExpanded(true)} className="mb-4">
        + New Matrix
      </Button>
    );
  }

  return (
    <Card className="mb-6">
      <CardTitle className="text-base mb-4">Create Parameter Sweep Matrix</CardTitle>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className="block text-sm font-medium mb-1">Name</label>
          <Input
            placeholder="e.g., Virtual Penetration vs Member Count"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Simulation Type</label>
          <select
            className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm"
            value={simType}
            onChange={(e) => {
              setSimType(e.target.value);
              setRowParam("");
              setColParam("");
              setOutputMetric("");
            }}
          >
            <option value="">Select type...</option>
            {Object.entries(simTypes).map(([key, cfg]) => (
              <option key={key} value={key}>
                {cfg.display_name}
              </option>
            ))}
          </select>
        </div>

        {typeConfig && (
          <>
            <div>
              <label className="block text-sm font-medium mb-1">Row Parameter</label>
              <select
                className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm"
                value={rowParam}
                onChange={(e) => setRowParam(e.target.value)}
              >
                <option value="">Select...</option>
                {params.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Column Parameter</label>
              <select
                className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm"
                value={colParam}
                onChange={(e) => setColParam(e.target.value)}
              >
                <option value="">Select...</option>
                {params.filter((p) => p !== rowParam).map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-xs font-medium mb-1">Row Start</label>
                <Input value={rowStart} onChange={(e) => setRowStart(e.target.value)} placeholder="0.10" />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1">Row End</label>
                <Input value={rowEnd} onChange={(e) => setRowEnd(e.target.value)} placeholder="0.50" />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1">Row Step</label>
                <Input value={rowStep} onChange={(e) => setRowStep(e.target.value)} placeholder="0.10" />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Column Values (comma-separated)
              </label>
              <Input
                value={colValues}
                onChange={(e) => setColValues(e.target.value)}
                placeholder="10000, 25000, 50000, 100000"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Output Metric</label>
              <select
                className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm"
                value={outputMetric}
                onChange={(e) => setOutputMetric(e.target.value)}
              >
                <option value="">Select...</option>
                {metrics.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs font-medium mb-1">Group Key (optional)</label>
                <Input
                  value={groupKey}
                  onChange={(e) => setGroupKey(e.target.value)}
                  placeholder="care_model"
                />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1">Group Value (optional)</label>
                <Input
                  value={groupValue}
                  onChange={(e) => setGroupValue(e.target.value)}
                  placeholder="virtual_blend"
                />
              </div>
            </div>
          </>
        )}
      </div>

      <div className="flex justify-end gap-2 mt-4">
        <Button variant="outline" onClick={() => setExpanded(false)}>
          Cancel
        </Button>
        <Button
          onClick={handleCreate}
          disabled={submitting || !simType || !rowParam || !colParam || !outputMetric}
        >
          {submitting ? "Creating..." : "Create Matrix"}
        </Button>
      </div>
    </Card>
  );
}

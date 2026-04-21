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

/** Generate values from start/end/step. */
function rangeValues(start: string, end: string, step: string): number[] {
  const s = parseFloat(start);
  const e = parseFloat(end);
  const st = parseFloat(step);
  if (isNaN(s) || isNaN(e) || isNaN(st) || st <= 0) return [];
  const vals: number[] = [];
  for (let v = s; v <= e + st / 100; v += st) {
    vals.push(Math.round(v * 1e10) / 1e10);
  }
  return vals;
}

export function MatrixBuilder({ analysisId, simTypes, onCreated }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [simType, setSimType] = useState("");
  const [name, setName] = useState("");

  // Row axis
  const [rowParam, setRowParam] = useState("");
  const [rowStart, setRowStart] = useState("");
  const [rowEnd, setRowEnd] = useState("");
  const [rowStep, setRowStep] = useState("");

  // Col axis
  const [colParam, setColParam] = useState("");
  const [colStart, setColStart] = useState("");
  const [colEnd, setColEnd] = useState("");
  const [colStep, setColStep] = useState("");

  // Output
  const [outputMetric, setOutputMetric] = useState("");
  const [groupKey, setGroupKey] = useState("");
  const [groupValue, setGroupValue] = useState("");

  // Base parameters (all params except row/col)
  const [baseParams, setBaseParams] = useState<Record<string, string>>({});

  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  const typeConfig = simType ? simTypes[simType] : null;
  const allParams = typeConfig ? Object.keys(typeConfig.parameters) : [];
  const metrics = typeConfig
    ? [
        typeConfig.aggregation.value_column,
        ...(typeConfig.aggregation.additional_metrics?.map((m) => m.value_column) ?? []),
      ]
    : [];

  // Base params = all params minus row and col axes
  const baseParamKeys = allParams.filter((p) => p !== rowParam && p !== colParam);

  const handleTypeChange = (type: string) => {
    setSimType(type);
    setRowParam("");
    setColParam("");
    setOutputMetric("");
    setGroupKey("");
    setGroupValue("");
    if (type && simTypes[type]) {
      const defaults: Record<string, string> = {};
      for (const [key, def] of Object.entries(simTypes[type]!.parameters)) {
        defaults[key] = String(def.default);
      }
      setBaseParams(defaults);
    } else {
      setBaseParams({});
    }
  };

  const handleCreate = async () => {
    setTouched(true);
    if (!isValid) return;
    setSubmitting(true);
    try {
      const rowVals = rangeValues(rowStart, rowEnd, rowStep);
      const colVals = rangeValues(colStart, colEnd, colStep);

      // Build base parameters (numeric, excluding row/col)
      const params: Record<string, unknown> = {};
      for (const key of baseParamKeys) {
        const val = baseParams[key];
        if (val === "true" || val === "false") {
          params[key] = val === "true";
        } else {
          const n = parseFloat(val ?? "");
          if (!isNaN(n)) params[key] = n;
        }
      }

      await api.post<Matrix>(`/analyses/${analysisId}/matrices`, {
        name: name || "Untitled Matrix",
        simulation_type: simType,
        row_parameter: rowParam,
        row_values: rowVals,
        col_parameter: colParam,
        col_values: colVals,
        base_parameters: params,
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

  // Preview generated values
  const rowPreview = rangeValues(rowStart, rowEnd, rowStep);
  const colPreview = rangeValues(colStart, colEnd, colStep);

  // Check base params: all non-boolean params must have a valid numeric value
  const missingBaseParams = baseParamKeys.filter((key) => {
    const def = typeConfig?.parameters[key];
    if (typeof def?.default === "boolean") return false;
    const val = baseParams[key];
    return !val || isNaN(parseFloat(val));
  });

  // Collect all validation errors
  const errors: string[] = [];
  if (!simType) errors.push("Select a simulation type");
  if (typeConfig && !rowParam) errors.push("Select a row parameter");
  if (typeConfig && !colParam) errors.push("Select a column parameter");
  if (typeConfig && rowPreview.length === 0 && (rowStart || rowEnd || rowStep))
    errors.push("Row range produces no values — check start/end/step");
  if (typeConfig && rowPreview.length === 0 && !rowStart && !rowEnd && !rowStep)
    errors.push("Enter row start, end, and step values");
  if (typeConfig && colPreview.length === 0 && (colStart || colEnd || colStep))
    errors.push("Column range produces no values — check start/end/step");
  if (typeConfig && colPreview.length === 0 && !colStart && !colEnd && !colStep)
    errors.push("Enter column start, end, and step values");
  if (typeConfig && !outputMetric) errors.push("Select an output metric");
  if (missingBaseParams.length > 0)
    errors.push(`Fill in base parameters: ${missingBaseParams.map((k) => k.replace(/_/g, " ")).join(", ")}`);

  const isValid = errors.length === 0;

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
      <div className="space-y-4">
        {/* Row 1: Name + Type */}
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
              onChange={(e) => handleTypeChange(e.target.value)}
            >
              <option value="">Select type...</option>
              {Object.entries(simTypes).map(([key, cfg]) => (
                <option key={key} value={key}>
                  {cfg.display_name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {typeConfig && (
          <>
            {/* Row/Col parameter selectors */}
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-sm font-medium mb-1">Row Parameter (vertical axis)</label>
                <select
                  className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm"
                  value={rowParam}
                  onChange={(e) => setRowParam(e.target.value)}
                >
                  <option value="">Select...</option>
                  {allParams.map((p) => (
                    <option key={p} value={p} disabled={p === colParam}>
                      {p.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Column Parameter (horizontal axis)</label>
                <select
                  className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm"
                  value={colParam}
                  onChange={(e) => setColParam(e.target.value)}
                >
                  <option value="">Select...</option>
                  {allParams.filter((p) => p !== rowParam).map((p) => (
                    <option key={p} value={p}>
                      {p.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Row range */}
            <div>
              <label className="block text-xs font-medium mb-1">
                Row Values — Start / End / Step
                {rowPreview.length > 0 && (
                  <span className="text-muted-foreground font-normal ml-2">
                    → {rowPreview.length} values: [{rowPreview.map((v) => v.toString()).join(", ")}]
                  </span>
                )}
              </label>
              <div className="grid grid-cols-3 gap-2">
                <Input value={rowStart} onChange={(e) => setRowStart(e.target.value)} placeholder="0.10" />
                <Input value={rowEnd} onChange={(e) => setRowEnd(e.target.value)} placeholder="0.50" />
                <Input value={rowStep} onChange={(e) => setRowStep(e.target.value)} placeholder="0.10" />
              </div>
            </div>

            {/* Col range */}
            <div>
              <label className="block text-xs font-medium mb-1">
                Column Values — Start / End / Step
                {colPreview.length > 0 && (
                  <span className="text-muted-foreground font-normal ml-2">
                    → {colPreview.length} values: [{colPreview.map((v) => v.toString()).join(", ")}]
                  </span>
                )}
              </label>
              <div className="grid grid-cols-3 gap-2">
                <Input value={colStart} onChange={(e) => setColStart(e.target.value)} placeholder="10000" />
                <Input value={colEnd} onChange={(e) => setColEnd(e.target.value)} placeholder="100000" />
                <Input value={colStep} onChange={(e) => setColStep(e.target.value)} placeholder="10000" />
              </div>
            </div>

            {/* Base parameters (everything except row/col axes) */}
            {baseParamKeys.length > 0 && (
              <div>
                <label className="block text-sm font-medium mb-2">Base Parameters</label>
                <p className="text-xs text-muted-foreground mb-2">
                  Fixed values for all cells. The row/col parameters above will be swept across their ranges.
                </p>
                <div className="grid gap-3 md:grid-cols-2">
                  {baseParamKeys.map((key) => {
                    const def = typeConfig.parameters[key];
                    return (
                      <div key={key}>
                        <label className="block text-xs text-muted-foreground mb-1">
                          {key.replace(/_/g, " ")}
                          {def?.description && (
                            <span className="ml-1 opacity-60">— {def.description}</span>
                          )}
                        </label>
                        {typeof def?.default === "boolean" ? (
                          <select
                            className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm font-mono"
                            value={baseParams[key] ?? String(def.default)}
                            onChange={(e) =>
                              setBaseParams((prev) => ({ ...prev, [key]: e.target.value }))
                            }
                          >
                            <option value="true">true</option>
                            <option value="false">false</option>
                          </select>
                        ) : (
                          <Input
                            value={baseParams[key] ?? ""}
                            onChange={(e) =>
                              setBaseParams((prev) => ({ ...prev, [key]: e.target.value }))
                            }
                            className="font-mono"
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Output metric */}
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <label className="block text-sm font-medium mb-1">Output Metric</label>
                <select
                  className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm"
                  value={outputMetric}
                  onChange={(e) => setOutputMetric(e.target.value)}
                >
                  <option value="">Select...</option>
                  {metrics.map((m) => (
                    <option key={m} value={m}>{m.replace(/_/g, " ")}</option>
                  ))}
                </select>
              </div>
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

            {/* Preview */}
            {rowPreview.length > 0 && colPreview.length > 0 && (
              <p className="text-xs text-muted-foreground bg-muted/50 rounded px-3 py-2">
                Matrix will create {rowPreview.length} × {colPreview.length} ={" "}
                {rowPreview.length * colPreview.length} cells
              </p>
            )}
          </>
        )}
      </div>

      {/* Validation errors */}
      {touched && errors.length > 0 && (
        <div className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive space-y-0.5">
          {errors.map((e) => (
            <p key={e}>• {e}</p>
          ))}
        </div>
      )}

      <div className="flex justify-end gap-2 mt-4">
        <Button variant="outline" onClick={() => setExpanded(false)}>
          Cancel
        </Button>
        <Button onClick={handleCreate} disabled={submitting}>
          {submitting ? "Creating..." : "Create Matrix"}
        </Button>
      </div>
    </Card>
  );
}

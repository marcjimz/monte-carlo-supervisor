import { useEffect, useState } from "react";
import { Play, HelpCircle } from "lucide-react";
import { api } from "../../lib/api";
import type { SimulationTypeConfig } from "../../lib/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Card, CardTitle } from "../ui/card";
import { Spinner } from "../ui/spinner";

const REQUIRED_PARAMS: Record<string, string[]> = {
  normal: ["loc", "scale"],
  lognormal: ["mean", "sigma"],
  beta: ["a", "b"],
  gamma: ["shape", "scale"],
  uniform: ["low", "high"],
};

const PARAM_INFO: Record<string, Record<string, { label: string; tooltip: string }>> = {
  normal: {
    loc: { label: "Mean", tooltip: "Center of the distribution — the average expected value" },
    scale: { label: "Std Dev", tooltip: "Standard deviation — how spread out values are around the mean" },
  },
  lognormal: {
    mean: { label: "Log Mean", tooltip: "Mean of the underlying log-transformed distribution" },
    sigma: { label: "Log Std Dev", tooltip: "Standard deviation of the log-transformed distribution" },
  },
  beta: {
    a: { label: "Alpha (\u03b1)", tooltip: "Shape parameter — higher values shift the distribution right" },
    b: { label: "Beta (\u03b2)", tooltip: "Shape parameter — higher values shift the distribution left" },
  },
  gamma: {
    shape: { label: "Shape (k)", tooltip: "Controls the shape of the curve — higher values make it more symmetric" },
    scale: { label: "Scale (\u03b8)", tooltip: "Stretches the distribution — higher values spread it wider" },
  },
  uniform: {
    low: { label: "Min", tooltip: "Minimum possible value — all values equally likely between min and max" },
    high: { label: "Max", tooltip: "Maximum possible value" },
  },
};

const DIST_TYPE_LABELS: Record<string, string> = {
  normal: "Normal (Gaussian)",
  lognormal: "Log-Normal",
  beta: "Beta",
  gamma: "Gamma",
  uniform: "Uniform",
};

const DIST_NAME_LABELS: Record<string, string> = {
  encounter_volume: "Volume",
  gross_charges: "Gross Charges",
  denial_rate: "Denial Rate",
  inperson_cost: "In-Person Cost",
  virtual_cost: "Virtual Cost",
  baseline_cost: "Baseline Cost",
  reduction_noise: "Reduction Noise",
};

interface DistOverride {
  enabled: boolean;
  type: string;
  params: Record<string, string>;
}

interface Props {
  onTriggered?: () => void;
}

export function SimulationBuilder({ onTriggered }: Props) {
  const [simTypes, setSimTypes] = useState<
    Record<string, SimulationTypeConfig>
  >({});
  const [expanded, setExpanded] = useState(false);
  const [simType, setSimType] = useState("");
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [numSims, setNumSims] = useState("10000");
  const [seed, setSeed] = useState("42");
  const [distOverrides, setDistOverrides] = useState<Record<string, DistOverride>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{
    status: string;
    run_id?: string;
    job_run_id?: number;
    message?: string;
  } | null>(null);

  useEffect(() => {
    api
      .get<{ simulation_types: Record<string, SimulationTypeConfig> }>(
        "/config/simulation-types",
      )
      .then((data) => setSimTypes(data.simulation_types))
      .catch(console.error);
  }, []);

  const typeConfig = simType ? simTypes[simType] : null;

  // Reset param values when type changes
  const handleTypeChange = (type: string) => {
    setSimType(type);
    setResult(null);
    if (type && simTypes[type]) {
      const defaults: Record<string, string> = {};
      for (const [key, def] of Object.entries(simTypes[type]!.parameters)) {
        defaults[key] = String(def.default);
      }
      setParamValues(defaults);

      // Initialize distribution overrides (all uncustomized by default)
      const overrides: Record<string, DistOverride> = {};
      for (const [name, def] of Object.entries(simTypes[type]!.distributions)) {
        overrides[name] = {
          enabled: false,
          type: def.default_spec.type,
          params: Object.fromEntries(
            Object.entries(def.default_spec.params).map(([k, v]) => [k, String(v)]),
          ),
        };
      }
      setDistOverrides(overrides);
    } else {
      setParamValues({});
      setDistOverrides({});
    }
  };

  const handleTrigger = async () => {
    if (!simType) return;
    setSubmitting(true);
    setResult(null);

    try {
      // Build numeric parameters
      const params: Record<string, unknown> = {};
      for (const [key, val] of Object.entries(paramValues)) {
        if (val === "true" || val === "false") {
          params[key] = val === "true";
        } else {
          const n = parseFloat(val);
          if (!isNaN(n)) params[key] = n;
        }
      }

      // Build distribution overrides from enabled entries
      const distribution_overrides: Record<string, { type: string; params: Record<string, number> }> = {};
      for (const [name, override] of Object.entries(distOverrides)) {
        if (override.enabled) {
          const numParams: Record<string, number> = {};
          for (const [k, v] of Object.entries(override.params)) {
            numParams[k] = parseFloat(v);
          }
          distribution_overrides[name] = { type: override.type, params: numParams };
        }
      }
      if (Object.keys(distribution_overrides).length > 0) {
        params.distribution_overrides = distribution_overrides;
      }

      const res = await api.post<{
        status: string;
        run_id?: string;
        job_run_id?: number;
        message?: string;
      }>("/simulations/trigger", {
        simulation_type: simType,
        parameters: params,
        num_simulations: parseInt(numSims) || 10000,
        seed: parseInt(seed) || 42,
      });

      setResult(res);
      onTriggered?.();
    } catch (err) {
      setResult({
        status: "error",
        message: err instanceof Error ? err.message : "Trigger failed",
      });
    } finally {
      setSubmitting(false);
    }
  };

  if (!expanded) {
    return (
      <Button
        variant="outline"
        onClick={() => setExpanded(true)}
        className="mb-4"
      >
        <Play className="h-3.5 w-3.5 mr-1.5" />
        New Simulation
      </Button>
    );
  }

  return (
    <Card className="mb-6">
      <div className="flex items-center justify-between mb-4">
        <CardTitle className="text-base">Run a Simulation</CardTitle>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setExpanded(false);
            setResult(null);
          }}
        >
          Cancel
        </Button>
      </div>

      <div className="space-y-4">
        {/* Type selector */}
        <div>
          <label className="block text-sm font-medium mb-1">
            Simulation Type
          </label>
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
          {typeConfig && (
            <p className="text-xs text-muted-foreground mt-1">
              {typeConfig.description}
            </p>
          )}
        </div>

        {/* Parameters */}
        {typeConfig && (
          <>
            <div>
              <label className="block text-sm font-medium mb-2">
                Parameters
              </label>
              <div className="grid gap-3 md:grid-cols-2">
                {Object.entries(typeConfig.parameters).map(([key, def]) => (
                  <div key={key}>
                    <label className="block text-xs text-muted-foreground mb-1">
                      {key.replace(/_/g, " ")}
                      {def.description && (
                        <span className="ml-1 opacity-60">
                          — {def.description}
                        </span>
                      )}
                    </label>
                    {typeof def.default === "boolean" ? (
                      <select
                        className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm font-mono"
                        value={paramValues[key] ?? String(def.default)}
                        onChange={(e) =>
                          setParamValues((prev) => ({
                            ...prev,
                            [key]: e.target.value,
                          }))
                        }
                      >
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    ) : (
                      <Input
                        value={paramValues[key] ?? ""}
                        onChange={(e) =>
                          setParamValues((prev) => ({
                            ...prev,
                            [key]: e.target.value,
                          }))
                        }
                        className="font-mono"
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Distribution overrides */}
            {Object.keys(typeConfig.distributions).length > 0 && (
              <DistributionEditor
                distributions={typeConfig.distributions}
                overrides={distOverrides}
                onChange={setDistOverrides}
              />
            )}

            {/* Trials + seed */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-muted-foreground mb-1">
                  Number of trials
                </label>
                <Input
                  value={numSims}
                  onChange={(e) => setNumSims(e.target.value)}
                  className="font-mono"
                />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">
                  Random seed
                </label>
                <Input
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  className="font-mono"
                />
              </div>
            </div>

            {/* Result feedback */}
            {result && (
              <div
                className={`rounded-md p-3 text-sm ${
                  result.status === "error"
                    ? "bg-destructive/10 text-destructive"
                    : "bg-success/10 text-success"
                }`}
              >
                {result.status === "error" ? (
                  <p>{result.message}</p>
                ) : (
                  <>
                    <p>
                      Simulation triggered.{" "}
                      {result.job_run_id && (
                        <span className="font-mono text-xs">
                          Job Run: {result.job_run_id}
                        </span>
                      )}
                      {result.run_id && !result.job_run_id && (
                        <span className="font-mono text-xs">
                          Run ID: {result.run_id}
                        </span>
                      )}
                    </p>
                    <p className="text-xs opacity-75 mt-1">
                      Simulation submitted. It will appear below shortly and
                      update to Completed when processing finishes.
                    </p>
                  </>
                )}
              </div>
            )}

            {/* Submit */}
            <div className="flex justify-end">
              <Button onClick={handleTrigger} disabled={submitting}>
                {submitting ? (
                  <>
                    <Spinner className="h-3.5 w-3.5 mr-1.5" />
                    Triggering...
                  </>
                ) : (
                  <>
                    <Play className="h-3.5 w-3.5 mr-1.5" />
                    Run Simulation
                  </>
                )}
              </Button>
            </div>
          </>
        )}
      </div>
    </Card>
  );
}

/** Interactive distribution editor with per-distribution customize toggle. */
function DistributionEditor({
  distributions,
  overrides,
  onChange,
}: {
  distributions: Record<
    string,
    { description: string; default_spec: { type: string; params: Record<string, number> } }
  >;
  overrides: Record<string, DistOverride>;
  onChange: (overrides: Record<string, DistOverride>) => void;
}) {
  const updateOverride = (name: string, patch: Partial<DistOverride>) => {
    const current = overrides[name];
    if (!current) return;
    onChange({ ...overrides, [name]: { ...current, ...patch } });
  };

  const handleTypeChange = (name: string, newType: string) => {
    const requiredKeys = REQUIRED_PARAMS[newType] ?? [];
    const newParams: Record<string, string> = {};
    for (const k of requiredKeys) {
      // Carry over value if same param key exists, otherwise default to "0"
      newParams[k] = overrides[name]?.params[k] ?? "0";
    }
    updateOverride(name, { type: newType, params: newParams });
  };

  const handleParamChange = (name: string, paramKey: string, value: string) => {
    const current = overrides[name]?.params ?? {};
    updateOverride(name, { params: { ...current, [paramKey]: value } });
  };

  return (
    <div>
      <label className="block text-sm font-medium mb-2">Distributions</label>
      <div className="space-y-2">
        {Object.entries(distributions).map(([name, dist]) => {
          const override = overrides[name];
          const isCustomized = override?.enabled ?? false;

          return (
            <div
              key={name}
              className="border border-border rounded-md bg-muted/30 px-3 py-2"
            >
              {/* Header row: name + customize toggle */}
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium">{DIST_NAME_LABELS[name] ?? name}</span>
                <label className="flex items-center gap-1.5 text-[10px] text-muted-foreground cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={isCustomized}
                    onChange={(e) =>
                      updateOverride(name, { enabled: e.target.checked })
                    }
                    className="h-3 w-3 rounded border-border"
                  />
                  Customize
                </label>
              </div>

              {isCustomized && override ? (
                /* Editable mode */
                <div className="mt-2 space-y-2">
                  {/* Type selector */}
                  <div>
                    <label className="block text-[10px] text-muted-foreground mb-0.5">
                      Distribution type
                    </label>
                    <select
                      className="flex h-8 w-full rounded-md border border-border bg-transparent px-2 py-1 text-xs"
                      value={override.type}
                      onChange={(e) => handleTypeChange(name, e.target.value)}
                    >
                      {Object.entries(DIST_TYPE_LABELS).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Param inputs */}
                  <div className="grid grid-cols-2 gap-2">
                    {(REQUIRED_PARAMS[override.type] ?? []).map((paramKey) => {
                      const info = PARAM_INFO[override.type]?.[paramKey];
                      return (
                        <div key={paramKey}>
                          <label className="flex items-center gap-1 text-[10px] text-muted-foreground mb-0.5">
                            {info?.label ?? paramKey}
                            {info?.tooltip && (
                              <span title={info.tooltip}>
                                <HelpCircle className="h-3 w-3 opacity-40 cursor-help" />
                              </span>
                            )}
                          </label>
                          <Input
                            value={override.params[paramKey] ?? ""}
                            onChange={(e) =>
                              handleParamChange(name, paramKey, e.target.value)
                            }
                            className="h-8 text-xs font-mono"
                          />
                        </div>
                      );
                    })}
                  </div>

                  {/* Description */}
                  {dist.description && (
                    <p className="text-[10px] text-muted-foreground">
                      {dist.description}
                    </p>
                  )}
                </div>
              ) : (
                /* Read-only mode */
                <p className="text-[10px] text-muted-foreground mt-1 font-mono">
                  {DIST_TYPE_LABELS[dist.default_spec.type] ?? dist.default_spec.type} (
                  {Object.entries(dist.default_spec.params)
                    .map(([k, v]) => {
                      const label = PARAM_INFO[dist.default_spec.type]?.[k]?.label ?? k;
                      return `${label}=${v}`;
                    })
                    .join(", ")}
                  ) — from historical data
                </p>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-[10px] text-muted-foreground mt-1.5">
        Uncustomized distributions use values fitted from historical data.
      </p>
    </div>
  );
}

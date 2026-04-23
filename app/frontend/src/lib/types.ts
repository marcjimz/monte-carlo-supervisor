/** TypeScript types mirroring Pydantic models. */

export interface User {
  email: string;
  username: string;
}

export interface Analysis {
  id: string;
  name: string;
  description: string | null;
  owner_email: string;
  status: "draft" | "published";
  created_at: string;
  updated_at: string;
}

export interface Collaborator {
  id: string;
  analysis_id: string;
  user_email: string;
  role: "viewer" | "editor";
  created_at: string;
}

export interface AnalysisSimulation {
  id: string;
  analysis_id: string;
  run_id: string;
  added_by: string;
  created_at: string;
}

export interface AnalysisDetail extends Analysis {
  collaborators: Collaborator[];
  simulations: AnalysisSimulation[];
}

export interface MatrixCell {
  id: string;
  matrix_id: string;
  row_value: number;
  col_value: number;
  run_id: string | null;
  status: "pending" | "queued" | "running" | "completed" | "failed";
  result_mean: number | null;
  result_p05: number | null;
  result_p50: number | null;
  result_p95: number | null;
  created_at: string;
  updated_at: string;
}

export interface Matrix {
  id: string;
  analysis_id: string;
  name: string;
  description: string | null;
  simulation_type: string;
  row_parameter: string;
  row_values: number[];
  col_parameter: string;
  col_values: number[];
  base_parameters: Record<string, unknown>;
  output_metric: string;
  output_group_key: string | null;
  output_group_value: string | null;
  num_simulations: number;
  seed: number;
  created_at: string;
  updated_at: string;
  cells: MatrixCell[];
}

export interface Message {
  id: string;
  thread_id: string;
  role: "user" | "assistant";
  content: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface Thread {
  id: string;
  analysis_id: string;
  owner_email: string;
  title: string;
  icon: string | null;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface SimulationRun {
  run_id: string;
  simulation_type: string;
  parameters: string;
  params_hash: string;
  seed: number;
  num_simulations: number;
  status: string;
  job_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SimulationResult {
  run_id: string;
  simulation_type: string;
  metric_name: string;
  group_key: string;
  group_value: string;
  num_trials: number;
  mean_value: number;
  std_value: number | null;
  min_value: number | null;
  max_value: number | null;
  p05: number | null;
  p10: number | null;
  p25: number | null;
  p50: number | null;
  p75: number | null;
  p90: number | null;
  p95: number | null;
  created_at: string;
}

export interface SimulationDetail extends SimulationRun {
  results: SimulationResult[];
}

export interface SimulationTriggeredEvent {
  run_id: string;
  simulation_type: string;
  parameters: string;
  params_hash: string;
  seed: number;
  num_simulations: number;
  status: string;
  job_run_id: string;
  created_at: string;
  updated_at: string;
}

export interface ChartDataEvent {
  chart_type: "line" | "bar";
  x_key: string;
  y_keys: string[];
  data: Record<string, unknown>[];
}

export interface MatrixCreatedEvent {
  id: string;
  name: string;
  simulation_type: string;
  row_parameter: string;
  col_parameter: string;
  rows: number;
  cols: number;
  total_cells: number;
  auto_running?: boolean;
}

export interface DistributionSpec {
  simulation_type: string;
  distribution_name: string;
  version: number;
  spec: string;
  fit_metadata: string | null;
  created_at: string;
}

export interface ParameterDef {
  default: number | boolean;
  description: string;
}

export interface DistributionDef {
  description: string;
  default_spec: {
    type: string;
    params: Record<string, number>;
  };
}

export interface SimulationTypeConfig {
  display_name: string;
  description: string;
  parameters: Record<string, ParameterDef>;
  distributions: Record<string, DistributionDef>;
  aggregation: {
    value_column: string;
    group_column: string;
    additional_metrics?: Array<{
      value_column: string;
      group_column: string;
    }>;
  };
  schema: string;
}

-- Monte Carlo Supervisor UI — Lakebase Schema
-- App-owned tables (CRUD) + Delta-synced tables (read-only)

-- ============================================================
-- App-owned tables
-- ============================================================

-- analyses
CREATE TABLE IF NOT EXISTS analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL DEFAULT 'Untitled Analysis',
    description     TEXT,
    owner_email     VARCHAR(320) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'published')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- analysis_collaborators
CREATE TABLE IF NOT EXISTS analysis_collaborators (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id     UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    user_email      VARCHAR(320) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'viewer'
                    CHECK (role IN ('viewer', 'editor')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(analysis_id, user_email)
);

-- analysis_simulations (links analyses to simulation run_ids)
CREATE TABLE IF NOT EXISTS analysis_simulations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id     UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    run_id          VARCHAR(64) NOT NULL,
    added_by        VARCHAR(320) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(analysis_id, run_id)
);

-- analysis_matrices (2D parameter sweep config)
CREATE TABLE IF NOT EXISTS analysis_matrices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id     UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL DEFAULT 'Untitled Matrix',
    simulation_type VARCHAR(50) NOT NULL,
    row_parameter   VARCHAR(100) NOT NULL,
    row_values      JSONB NOT NULL,
    col_parameter   VARCHAR(100) NOT NULL,
    col_values      JSONB NOT NULL,
    base_parameters JSONB NOT NULL DEFAULT '{}',
    output_metric   VARCHAR(100) NOT NULL,
    output_group_key VARCHAR(100),
    output_group_value VARCHAR(100),
    num_simulations INT NOT NULL DEFAULT 10000,
    seed            INT NOT NULL DEFAULT 42,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- matrix_cells (one per row/col combination)
CREATE TABLE IF NOT EXISTS matrix_cells (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matrix_id       UUID NOT NULL REFERENCES analysis_matrices(id) ON DELETE CASCADE,
    row_value       DOUBLE PRECISION NOT NULL,
    col_value       DOUBLE PRECISION NOT NULL,
    run_id          VARCHAR(64),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'queued', 'running', 'completed', 'failed')),
    result_mean     DOUBLE PRECISION,
    result_p05      DOUBLE PRECISION,
    result_p50      DOUBLE PRECISION,
    result_p95      DOUBLE PRECISION,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(matrix_id, row_value, col_value)
);

-- agent_threads
CREATE TABLE IF NOT EXISTS agent_threads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id     UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    owner_email     VARCHAR(320) NOT NULL,
    title           VARCHAR(255) NOT NULL DEFAULT 'New Thread',
    icon            VARCHAR(50) DEFAULT 'chat',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- thread_messages
CREATE TABLE IF NOT EXISTS thread_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id       UUID NOT NULL REFERENCES agent_threads(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Delta-synced tables (read-only mirrors)
-- ============================================================

-- sync_simulation_runs
CREATE TABLE IF NOT EXISTS sync_simulation_runs (
    run_id          VARCHAR(64) PRIMARY KEY,
    simulation_type VARCHAR(50) NOT NULL,
    parameters      TEXT NOT NULL,
    params_hash     VARCHAR(64) NOT NULL,
    seed            INT NOT NULL,
    num_simulations INT NOT NULL,
    status          VARCHAR(20) NOT NULL,
    job_run_id      VARCHAR(64),
    created_at      VARCHAR(50) NOT NULL,
    updated_at      VARCHAR(50) NOT NULL,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- sync_simulation_results
CREATE TABLE IF NOT EXISTS sync_simulation_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          VARCHAR(64) NOT NULL,
    simulation_type VARCHAR(50) NOT NULL,
    metric_name     VARCHAR(100) NOT NULL,
    group_key       VARCHAR(100) NOT NULL,
    group_value     VARCHAR(100) NOT NULL,
    num_trials      BIGINT NOT NULL,
    mean_value      DOUBLE PRECISION NOT NULL,
    std_value       DOUBLE PRECISION,
    min_value       DOUBLE PRECISION,
    max_value       DOUBLE PRECISION,
    p05             DOUBLE PRECISION,
    p10             DOUBLE PRECISION,
    p25             DOUBLE PRECISION,
    p50             DOUBLE PRECISION,
    p75             DOUBLE PRECISION,
    p90             DOUBLE PRECISION,
    p95             DOUBLE PRECISION,
    created_at      VARCHAR(50) NOT NULL,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- sync_distribution_specs
CREATE TABLE IF NOT EXISTS sync_distribution_specs (
    id              BIGSERIAL PRIMARY KEY,
    simulation_type VARCHAR(50) NOT NULL,
    distribution_name VARCHAR(100) NOT NULL,
    version         INT NOT NULL,
    spec            TEXT NOT NULL,
    fit_metadata    TEXT,
    created_at      VARCHAR(50) NOT NULL,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- sync metadata tracking
CREATE TABLE IF NOT EXISTS sync_metadata (
    table_name      VARCHAR(100) PRIMARY KEY,
    last_synced_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Indexes for common queries
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_analyses_owner ON analyses(owner_email);
CREATE INDEX IF NOT EXISTS idx_collaborators_user ON analysis_collaborators(user_email);
CREATE INDEX IF NOT EXISTS idx_collaborators_analysis ON analysis_collaborators(analysis_id);
CREATE INDEX IF NOT EXISTS idx_analysis_sims_analysis ON analysis_simulations(analysis_id);
CREATE INDEX IF NOT EXISTS idx_matrices_analysis ON analysis_matrices(analysis_id);
CREATE INDEX IF NOT EXISTS idx_cells_matrix ON matrix_cells(matrix_id);
CREATE INDEX IF NOT EXISTS idx_threads_analysis ON agent_threads(analysis_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON thread_messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_sync_runs_type ON sync_simulation_runs(simulation_type);
CREATE INDEX IF NOT EXISTS idx_sync_results_run ON sync_simulation_results(run_id);
CREATE INDEX IF NOT EXISTS idx_sync_specs_type ON sync_distribution_specs(simulation_type);

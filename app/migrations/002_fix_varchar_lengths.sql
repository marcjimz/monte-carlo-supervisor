-- Fix VARCHAR(30) columns that are too narrow for Databricks timestamps
ALTER TABLE sync_simulation_runs ALTER COLUMN created_at TYPE VARCHAR(50);
ALTER TABLE sync_simulation_runs ALTER COLUMN updated_at TYPE VARCHAR(50);
ALTER TABLE sync_simulation_results ALTER COLUMN created_at TYPE VARCHAR(50);
ALTER TABLE sync_distribution_specs ALTER COLUMN created_at TYPE VARCHAR(50);

-- Add description column to analysis_matrices
ALTER TABLE analysis_matrices ADD COLUMN IF NOT EXISTS description TEXT;

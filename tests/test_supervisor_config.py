"""Tests for supervisor, Genie, and metric view configuration — pure Python, no Spark required."""

from src.databricks.agentbricks.supervisor import get_supervisor_config
from src.databricks.agentbricks.examples import get_supervisor_examples
from src.databricks.genie.space_config import get_genie_space_config
from src.databricks.genie.sample_questions import get_sample_questions
from src.databricks.metric_views.definitions import get_metric_view_definitions
from src.databricks.monte_carlo.results import compute_cache_key, get_simulation_tables_ddl

# Dummy catalog/schema values used throughout tests
CATALOG = "test_catalog"
SCHEMA = "test_schema"
GENIE_SPACE_ID = "genie-space-123"


# ---------------------------------------------------------------------------
# Supervisor config
# ---------------------------------------------------------------------------


class TestSupervisorConfig:
    def test_returns_dict_with_required_keys(self):
        cfg = get_supervisor_config(GENIE_SPACE_ID, CATALOG, SCHEMA)
        assert isinstance(cfg, dict)
        for key in ("name", "description", "agents", "instructions"):
            assert key in cfg, f"Missing key: {key}"

    def test_has_two_agents(self):
        cfg = get_supervisor_config(GENIE_SPACE_ID, CATALOG, SCHEMA)
        assert len(cfg["agents"]) == 2

    def test_agent_names(self):
        cfg = get_supervisor_config(GENIE_SPACE_ID, CATALOG, SCHEMA)
        names = {a["name"] for a in cfg["agents"]}
        assert names == {"encounter_analytics", "monte_carlo_simulator"}

    def test_agents_have_required_fields(self):
        cfg = get_supervisor_config(GENIE_SPACE_ID, CATALOG, SCHEMA)
        for agent in cfg["agents"]:
            assert "name" in agent
            assert "description" in agent


# ---------------------------------------------------------------------------
# Supervisor examples
# ---------------------------------------------------------------------------


class TestSupervisorExamples:
    def test_returns_list_of_dicts(self):
        examples = get_supervisor_examples()
        assert isinstance(examples, list)
        assert len(examples) > 0
        for ex in examples:
            assert isinstance(ex, dict)

    def test_example_keys(self):
        examples = get_supervisor_examples()
        for ex in examples:
            assert "question" in ex
            assert "guideline" in ex


# ---------------------------------------------------------------------------
# Genie space config
# ---------------------------------------------------------------------------


class TestGenieSpaceConfig:
    def test_returns_dict_with_required_keys(self):
        cfg = get_genie_space_config(CATALOG, SCHEMA)
        assert isinstance(cfg, dict)
        for key in ("display_name", "tables", "instructions"):
            assert key in cfg, f"Missing key: {key}"

    def test_tables_reference_catalog_schema(self):
        cfg = get_genie_space_config(CATALOG, SCHEMA)
        for table in cfg["tables"]:
            assert table.startswith(f"{CATALOG}.{SCHEMA}.")


# ---------------------------------------------------------------------------
# Genie sample questions
# ---------------------------------------------------------------------------


class TestGenieSampleQuestions:
    def test_returns_list_of_dicts(self):
        questions = get_sample_questions()
        assert isinstance(questions, list)
        assert len(questions) > 0

    def test_question_keys(self):
        questions = get_sample_questions()
        for q in questions:
            assert "question" in q
            assert "description" in q


# ---------------------------------------------------------------------------
# Metric view definitions
# ---------------------------------------------------------------------------


class TestMetricViewDDL:
    def test_returns_six_views(self):
        views = get_metric_view_definitions(CATALOG, SCHEMA)
        assert isinstance(views, list)
        assert len(views) == 6

    def test_each_view_contains_create_and_metrics(self):
        views = get_metric_view_definitions(CATALOG, SCHEMA)
        for view in views:
            sql = view["sql"]
            assert "CREATE OR REPLACE VIEW" in sql
            assert "WITH METRICS" in sql

    def test_views_reference_catalog_schema(self):
        views = get_metric_view_definitions(CATALOG, SCHEMA)
        for view in views:
            assert f"{CATALOG}.{SCHEMA}." in view["sql"]


# ---------------------------------------------------------------------------
# Simulation tables DDL
# ---------------------------------------------------------------------------


class TestSimulationTablesDDL:
    def test_returns_three_ddl_strings(self):
        ddls = get_simulation_tables_ddl(CATALOG, SCHEMA)
        assert isinstance(ddls, list)
        assert len(ddls) == 3

    def test_each_ddl_is_create_table(self):
        ddls = get_simulation_tables_ddl(CATALOG, SCHEMA)
        for ddl in ddls:
            assert isinstance(ddl, str)
            assert "CREATE TABLE IF NOT EXISTS" in ddl

    def test_ddl_references_catalog_schema(self):
        ddls = get_simulation_tables_ddl(CATALOG, SCHEMA)
        for ddl in ddls:
            assert f"{CATALOG}.{SCHEMA}." in ddl


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_deterministic(self):
        key1 = compute_cache_key("patient_volume", '{"department": "ER"}', 42, 10000)
        key2 = compute_cache_key("patient_volume", '{"department": "ER"}', 42, 10000)
        assert key1 == key2

    def test_sha256_hex_format(self):
        key = compute_cache_key("patient_volume", '{}', 42, 100)
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_different_type_produces_different_hash(self):
        key1 = compute_cache_key("patient_volume", '{}', 42, 100)
        key2 = compute_cache_key("revenue", '{}', 42, 100)
        assert key1 != key2

    def test_different_params_produces_different_hash(self):
        key1 = compute_cache_key("patient_volume", '{"a": 1}', 42, 100)
        key2 = compute_cache_key("patient_volume", '{"a": 2}', 42, 100)
        assert key1 != key2

    def test_different_seed_produces_different_hash(self):
        key1 = compute_cache_key("patient_volume", '{}', 42, 100)
        key2 = compute_cache_key("patient_volume", '{}', 99, 100)
        assert key1 != key2

    def test_different_num_simulations_produces_different_hash(self):
        key1 = compute_cache_key("patient_volume", '{}', 42, 100)
        key2 = compute_cache_key("patient_volume", '{}', 42, 200)
        assert key1 != key2

    def test_param_order_does_not_matter(self):
        key1 = compute_cache_key("revenue", '{"a": 1, "b": 2}', 42, 100)
        key2 = compute_cache_key("revenue", '{"b": 2, "a": 1}', 42, 100)
        assert key1 == key2

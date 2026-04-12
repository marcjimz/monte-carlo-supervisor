"""Tests for supervisor, Genie, and metric view configuration — Women's Health focus.

Validates that generated configs match the AgentBricks API contract
(BaseAgentDict, MultiAgentSupervisorExampleDict) and that all simulation
types from config.yaml are propagated to instructions, examples, and agents.
"""

from src.databricks.agentbricks.supervisor import (
    get_supervisor_config,
    get_supervisor_agents,
    get_supervisor_instructions,
)
from src.databricks.agentbricks.examples import get_supervisor_examples
from src.databricks.genie.space_config import get_genie_space_config
from src.databricks.genie.sample_questions import get_sample_questions
from src.databricks.metric_views.definitions import (
    get_base_view_definitions,
    get_metric_view_definitions,
)
from src.databricks.monte_carlo import config_loader
from src.databricks.monte_carlo.results import compute_cache_key, get_simulation_tables_ddl
from src.databricks.sql.connections.workspace import WorkspaceConnection

# Dummy catalog/schema values used throughout tests
CATALOG = "test_catalog"
SCHEMA = "test_schema"
GENIE_SPACE_ID = "genie-space-123"

# Valid agent_type values from BaseAgentDict in AgentBricks models.py
VALID_AGENT_TYPES = {"genie", "serving_endpoint", "unity_catalog_function", "external_mcp_server", "ka", "app"}


# ---------------------------------------------------------------------------
# Supervisor config — structure
# ---------------------------------------------------------------------------


class TestSupervisorConfig:
    def test_returns_dict_with_required_keys(self):
        cfg = get_supervisor_config(GENIE_SPACE_ID, CATALOG, SCHEMA)
        assert isinstance(cfg, dict)
        for key in ("name", "description", "agents", "instructions"):
            assert key in cfg, f"Missing key: {key}"

    def test_has_four_agents(self):
        cfg = get_supervisor_config(GENIE_SPACE_ID, CATALOG, SCHEMA)
        assert len(cfg["agents"]) == 4

    def test_agent_names(self):
        cfg = get_supervisor_config(GENIE_SPACE_ID, CATALOG, SCHEMA)
        names = {a["name"] for a in cfg["agents"]}
        assert names == {"encounter_analytics", "simulation_checker", "simulation_trigger", "distribution_catalog"}

    def test_agents_have_required_fields(self):
        """Every agent must have name, description, agent_type per BaseAgentDict."""
        cfg = get_supervisor_config(GENIE_SPACE_ID, CATALOG, SCHEMA)
        for agent in cfg["agents"]:
            assert "name" in agent
            assert "description" in agent
            assert "agent_type" in agent

    def test_description_mentions_womens_health(self):
        cfg = get_supervisor_config(GENIE_SPACE_ID, CATALOG, SCHEMA)
        desc = cfg["description"].lower()
        assert "women" in desc or "health" in desc


# ---------------------------------------------------------------------------
# Supervisor agents — API contract validation
# ---------------------------------------------------------------------------


class TestSupervisorAgentsContract:
    """Validate agent dicts match the AgentBricks BaseAgentDict contract."""

    def test_agent_types_are_valid(self):
        """agent_type must be a known AgentBricks type."""
        agents = get_supervisor_agents(GENIE_SPACE_ID, CATALOG, SCHEMA)
        for agent in agents:
            assert agent["agent_type"] in VALID_AGENT_TYPES, (
                f"Agent '{agent['name']}' has invalid agent_type '{agent['agent_type']}'. "
                f"Valid types: {VALID_AGENT_TYPES}"
            )

    def test_genie_agent_has_space_id(self):
        """Genie agent must have genie_space.id per API contract."""
        agents = get_supervisor_agents(GENIE_SPACE_ID, CATALOG, SCHEMA)
        genie = [a for a in agents if a["agent_type"] == "genie"][0]
        assert "genie_space" in genie, "Genie agent missing genie_space key"
        assert "id" in genie["genie_space"], "Genie agent missing genie_space.id"
        assert genie["genie_space"]["id"] == GENIE_SPACE_ID

    def test_uc_function_agents_have_uc_path(self):
        """UC function agents must have unity_catalog_function.uc_path.{catalog,schema,name}."""
        agents = get_supervisor_agents(GENIE_SPACE_ID, CATALOG, SCHEMA)
        uc_agents = [a for a in agents if a["agent_type"] == "unity_catalog_function"]
        assert len(uc_agents) == 3, f"Expected 3 UC function agents, got {len(uc_agents)}"

        for agent in uc_agents:
            assert "unity_catalog_function" in agent, (
                f"Agent '{agent['name']}' missing unity_catalog_function key"
            )
            uc_cfg = agent["unity_catalog_function"]
            assert "uc_path" in uc_cfg, f"Agent '{agent['name']}' missing uc_path"
            for field in ("catalog", "schema", "name"):
                assert field in uc_cfg["uc_path"], (
                    f"Agent '{agent['name']}' missing uc_path.{field}"
                )

    def test_checker_points_to_check_simulation(self):
        agents = get_supervisor_agents(GENIE_SPACE_ID, CATALOG, SCHEMA)
        checker = [a for a in agents if a["name"] == "simulation_checker"][0]
        uc_path = checker["unity_catalog_function"]["uc_path"]
        assert uc_path["catalog"] == CATALOG
        assert uc_path["schema"] == SCHEMA
        assert uc_path["name"] == "check_simulation"

    def test_trigger_points_to_trigger_simulation(self):
        agents = get_supervisor_agents(GENIE_SPACE_ID, CATALOG, SCHEMA)
        trigger = [a for a in agents if a["name"] == "simulation_trigger"][0]
        uc_path = trigger["unity_catalog_function"]["uc_path"]
        assert uc_path["catalog"] == CATALOG
        assert uc_path["schema"] == SCHEMA
        assert uc_path["name"] == "trigger_simulation"

    def test_distribution_catalog_points_to_list_distributions(self):
        agents = get_supervisor_agents(GENIE_SPACE_ID, CATALOG, SCHEMA)
        catalog_agent = [a for a in agents if a["name"] == "distribution_catalog"][0]
        uc_path = catalog_agent["unity_catalog_function"]["uc_path"]
        assert uc_path["catalog"] == CATALOG
        assert uc_path["schema"] == SCHEMA
        assert uc_path["name"] == "list_distributions"

    def test_agents_have_no_extra_type_specific_keys(self):
        """Each agent should only have the type-specific key matching its agent_type."""
        type_to_key = {
            "genie": "genie_space",
            "unity_catalog_function": "unity_catalog_function",
            "serving_endpoint": "serving_endpoint",
            "app": "app",
            "external_mcp_server": "external_mcp_server",
        }
        all_type_keys = set(type_to_key.values())

        agents = get_supervisor_agents(GENIE_SPACE_ID, CATALOG, SCHEMA)
        for agent in agents:
            expected_key = type_to_key.get(agent["agent_type"])
            present_type_keys = set(agent.keys()) & all_type_keys
            assert present_type_keys == {expected_key}, (
                f"Agent '{agent['name']}' (type={agent['agent_type']}) has type-specific keys "
                f"{present_type_keys} but should only have {{{expected_key}}}"
            )


# ---------------------------------------------------------------------------
# Supervisor agents — config.yaml consistency
# ---------------------------------------------------------------------------


class TestSupervisorAgentsConfigConsistency:
    """Ensure agent descriptions stay in sync with config.yaml."""

    def test_checker_description_lists_all_sim_types(self):
        """simulation_checker description must mention every type from config."""
        agents = get_supervisor_agents(GENIE_SPACE_ID, CATALOG, SCHEMA)
        checker = [a for a in agents if a["name"] == "simulation_checker"][0]
        desc = checker["description"]
        for sim_type in config_loader.get_valid_types():
            assert sim_type in desc, (
                f"simulation_checker description missing type '{sim_type}'"
            )

    def test_trigger_description_lists_all_sim_types(self):
        """simulation_trigger description must mention every type from config."""
        agents = get_supervisor_agents(GENIE_SPACE_ID, CATALOG, SCHEMA)
        trigger = [a for a in agents if a["name"] == "simulation_trigger"][0]
        desc = trigger["description"]
        for sim_type in config_loader.get_valid_types():
            assert sim_type in desc, (
                f"simulation_trigger description missing type '{sim_type}'"
            )


# ---------------------------------------------------------------------------
# Supervisor instructions — config.yaml consistency
# ---------------------------------------------------------------------------


class TestSupervisorInstructions:
    """Validate instructions are complete and reference all config types."""

    def test_instructions_reference_all_sim_types(self):
        """Every simulation type from config must appear in the instructions."""
        instructions = get_supervisor_instructions()
        for sim_type in config_loader.get_valid_types():
            assert sim_type in instructions, (
                f"Instructions missing simulation type '{sim_type}'"
            )

    def test_instructions_contain_workflow_steps(self):
        """Instructions must describe the check → trigger → poll workflow."""
        instructions = get_supervisor_instructions()
        assert "simulation_checker" in instructions
        assert "simulation_trigger" in instructions
        assert "not_found" in instructions
        assert "completed" in instructions
        assert "running" in instructions

    def test_instructions_contain_parameter_names(self):
        """Instructions should mention parameter names for each sim type."""
        instructions = get_supervisor_instructions()
        for sim_type in config_loader.get_valid_types():
            defaults = config_loader.get_default_params(sim_type)
            # At least one parameter name from each type should appear
            found = any(param_name in instructions for param_name in defaults)
            assert found, (
                f"Instructions contain no parameter names for type '{sim_type}'. "
                f"Expected at least one of: {list(defaults.keys())}"
            )

    def test_instructions_mention_distribution_catalog(self):
        """Instructions should route distribution questions to distribution_catalog."""
        instructions = get_supervisor_instructions()
        assert "distribution_catalog" in instructions

    def test_instructions_are_non_trivial_length(self):
        """Instructions should be substantial (routing + workflow + params)."""
        instructions = get_supervisor_instructions()
        assert len(instructions) > 500, (
            f"Instructions seem too short ({len(instructions)} chars) — "
            "may be missing parameter reference or workflow description"
        )


# ---------------------------------------------------------------------------
# Supervisor examples — API contract + completeness
# ---------------------------------------------------------------------------


class TestSupervisorExamples:
    """Validate examples match AgentBricks API contract and cover all types."""

    def test_returns_list_of_dicts(self):
        examples = get_supervisor_examples()
        assert isinstance(examples, list)
        assert len(examples) > 0
        for ex in examples:
            assert isinstance(ex, dict)

    def test_example_keys_match_api_contract(self):
        """Each example must have 'question' and 'guideline' keys
        (mas_add_examples_batch reads these exact keys)."""
        examples = get_supervisor_examples()
        for ex in examples:
            assert "question" in ex, f"Example missing 'question' key: {ex}"
            assert "guideline" in ex, f"Example missing 'guideline' key: {ex}"

    def test_examples_have_non_empty_values(self):
        """No empty strings — these would be silently skipped by the API."""
        examples = get_supervisor_examples()
        for i, ex in enumerate(examples):
            assert ex["question"].strip(), f"Example {i} has empty question"
            assert ex["guideline"].strip(), f"Example {i} has empty guideline"

    def test_no_duplicate_questions(self):
        """Duplicate questions waste API calls and clutter the examples list."""
        examples = get_supervisor_examples()
        questions = [ex["question"] for ex in examples]
        duplicates = [q for q in questions if questions.count(q) > 1]
        assert not duplicates, f"Duplicate example questions: {set(duplicates)}"

    def test_every_sim_type_has_at_least_one_example(self):
        """Each simulation type from config.yaml should have a routing example."""
        examples = get_supervisor_examples()
        all_guidelines = " ".join(ex["guideline"] for ex in examples)
        for sim_type in config_loader.get_valid_types():
            assert sim_type in all_guidelines, (
                f"No example guideline references simulation type '{sim_type}'"
            )

    def test_simulation_examples_reference_appropriate_agent(self):
        """Simulation examples referencing a sim type should route to simulation_checker or distribution_catalog."""
        examples = get_supervisor_examples()
        sim_types = set(config_loader.get_valid_types())
        for ex in examples:
            guideline = ex["guideline"]
            # If the guideline references a sim type, it should mention an appropriate agent
            if any(st in guideline for st in sim_types):
                assert "simulation_checker" in guideline or "distribution_catalog" in guideline, (
                    f"Example references a sim type but doesn't route to simulation_checker or distribution_catalog: "
                    f"'{ex['question']}'"
                )

    def test_has_genie_routing_examples(self):
        """At least one example should route to encounter_analytics for historical queries."""
        examples = get_supervisor_examples()
        genie_examples = [
            ex for ex in examples if "encounter_analytics" in ex["guideline"]
        ]
        assert len(genie_examples) >= 1, "No examples route to encounter_analytics (Genie)"

    def test_has_distribution_catalog_example(self):
        """At least one example should route to distribution_catalog."""
        examples = get_supervisor_examples()
        dist_examples = [
            ex for ex in examples if "distribution_catalog" in ex["guideline"]
        ]
        assert len(dist_examples) >= 1, "No examples route to distribution_catalog"

    def test_has_compound_example(self):
        """At least one compound example (historical + simulation) should exist."""
        examples = get_supervisor_examples()
        compound = [
            ex for ex in examples
            if "encounter_analytics" in ex["guideline"] and "simulation_checker" in ex["guideline"]
        ]
        assert len(compound) >= 1, "No compound examples (historical + simulation routing)"


# ---------------------------------------------------------------------------
# WorkspaceConnection — OAuth M2M only (no bearer fallback)
# ---------------------------------------------------------------------------


class TestWorkspaceConnection:
    """Validate UC HTTP Connection DDL generation (OAuth M2M only)."""

    def test_no_bearer_method_exists(self):
        """get_create_bearer_sql must not exist — PAT fallback was removed."""
        assert not hasattr(WorkspaceConnection, "get_create_bearer_sql"), (
            "WorkspaceConnection still has get_create_bearer_sql — bearer fallback should be removed"
        )

    def test_oauth_m2m_sql_creates_connection(self):
        sql = WorkspaceConnection.get_create_oauth_m2m_sql(
            workspace_url="https://example.azuredatabricks.net",
            client_id="test-client-id",
            client_secret="test-secret",
        )
        assert "CREATE CONNECTION" in sql
        assert "TYPE HTTP" in sql

    def test_oauth_m2m_sql_contains_required_options(self):
        sql = WorkspaceConnection.get_create_oauth_m2m_sql(
            workspace_url="https://example.azuredatabricks.net",
            client_id="test-client-id",
            client_secret="test-secret",
        )
        assert "client_id" in sql
        assert "client_secret" in sql
        assert "oauth_scope" in sql
        assert "token_endpoint" in sql

    def test_oauth_m2m_derives_token_endpoint(self):
        sql = WorkspaceConnection.get_create_oauth_m2m_sql(
            workspace_url="https://example.azuredatabricks.net",
            client_id="x",
            client_secret="y",
        )
        assert "https://example.azuredatabricks.net/oidc/v1/token" in sql

    def test_oauth_m2m_strips_trailing_slash(self):
        sql = WorkspaceConnection.get_create_oauth_m2m_sql(
            workspace_url="https://example.azuredatabricks.net/",
            client_id="x",
            client_secret="y",
        )
        # Should not have double slashes
        assert "azuredatabricks.net//oidc" not in sql
        assert "azuredatabricks.net/oidc/v1/token" in sql

    def test_oauth_m2m_custom_connection_name(self):
        sql = WorkspaceConnection.get_create_oauth_m2m_sql(
            workspace_url="https://example.azuredatabricks.net",
            client_id="x",
            client_secret="y",
            connection_name="my_custom_conn",
        )
        assert "my_custom_conn" in sql

    def test_drop_sql(self):
        sql = WorkspaceConnection.get_drop_sql(connection_name="test_conn")
        assert sql == "DROP CONNECTION IF EXISTS test_conn"

    def test_grant_sql(self):
        sql = WorkspaceConnection.get_grant_sql(
            connection_name="test_conn", principal="data_team"
        )
        assert "GRANT USE_CONNECTION" in sql
        assert "test_conn" in sql
        assert "`data_team`" in sql


# ---------------------------------------------------------------------------
# Genie space config
# ---------------------------------------------------------------------------


class TestGenieSpaceConfig:
    def test_returns_dict_with_required_keys(self):
        cfg = get_genie_space_config(CATALOG, SCHEMA)
        assert isinstance(cfg, dict)
        for key in ("display_name", "description", "tables", "instructions"):
            assert key in cfg, f"Missing key: {key}"

    def test_no_warehouse_id_in_config(self):
        cfg = get_genie_space_config(CATALOG, SCHEMA)
        assert "warehouse_id" not in cfg, "warehouse_id should be auto-detected at runtime"

    def test_tables_reference_catalog_schema(self):
        cfg = get_genie_space_config(CATALOG, SCHEMA)
        for table in cfg["tables"]:
            assert table.startswith(f"{CATALOG}.{SCHEMA}.")

    def test_display_name_is_womens_health(self):
        cfg = get_genie_space_config(CATALOG, SCHEMA)
        assert "Women" in cfg["display_name"]


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


class TestBaseViewDDL:
    def test_returns_three_base_views(self):
        views = get_base_view_definitions(CATALOG, SCHEMA)
        assert isinstance(views, list)
        assert len(views) == 3

    def test_each_base_view_is_regular_sql_view(self):
        views = get_base_view_definitions(CATALOG, SCHEMA)
        for view in views:
            sql = view["sql"]
            assert "CREATE OR REPLACE VIEW" in sql
            assert "WITH METRICS" not in sql
            assert "JOIN" in sql


class TestMetricViewDDL:
    def test_returns_four_views(self):
        views = get_metric_view_definitions(CATALOG, SCHEMA)
        assert isinstance(views, list)
        assert len(views) == 4

    def test_each_view_contains_create_and_metrics(self):
        views = get_metric_view_definitions(CATALOG, SCHEMA)
        for view in views:
            sql = view["sql"]
            assert "CREATE OR REPLACE VIEW" in sql
            assert "WITH METRICS" in sql

    def test_no_joins_in_metric_view_source(self):
        """Metric view YAML source must be a single table/view, not a JOIN."""
        views = get_metric_view_definitions(CATALOG, SCHEMA)
        for view in views:
            sql = view["sql"]
            # Extract the source line from YAML
            for line in sql.split("\n"):
                stripped = line.strip()
                if stripped.startswith("source:"):
                    assert "JOIN" not in stripped, (
                        f"Metric view {view['name']} has JOIN in source field"
                    )

    def test_views_reference_catalog_schema(self):
        views = get_metric_view_definitions(CATALOG, SCHEMA)
        for view in views:
            assert f"{CATALOG}.{SCHEMA}." in view["sql"]

    def test_wh_view_names(self):
        """All metric views should have WH prefix."""
        views = get_metric_view_definitions(CATALOG, SCHEMA)
        for view in views:
            assert view["name"].startswith("mv_wh_"), (
                f"View {view['name']} should start with mv_wh_"
            )


# ---------------------------------------------------------------------------
# Simulation tables DDL
# ---------------------------------------------------------------------------


class TestSimulationTablesDDL:
    def test_returns_four_ddl_strings(self):
        ddls = get_simulation_tables_ddl(CATALOG, SCHEMA)
        assert isinstance(ddls, list)
        assert len(ddls) == 4

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

    def test_distribution_version_changes_hash(self):
        key1 = compute_cache_key("patient_volume", '{}', 42, 100, distribution_version=1)
        key2 = compute_cache_key("patient_volume", '{}', 42, 100, distribution_version=2)
        assert key1 != key2

    def test_default_distribution_version_matches_none(self):
        key1 = compute_cache_key("patient_volume", '{}', 42, 100, distribution_version=None)
        key2 = compute_cache_key("patient_volume", '{}', 42, 100, distribution_version="default")
        assert key1 == key2

    def test_distribution_version_vs_no_version(self):
        """A specific version should differ from default."""
        key1 = compute_cache_key("patient_volume", '{}', 42, 100)
        key2 = compute_cache_key("patient_volume", '{}', 42, 100, distribution_version=1)
        assert key1 != key2

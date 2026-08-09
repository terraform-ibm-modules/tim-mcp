"""
Tests for the generate_module_composition tool implementation.

The tool is backed by baked-in knowledge (static/compositions.json) and resolves
module versions from static/module_index.json, so these tests exercise the real
catalog without any network access.
"""

import pytest

from tim_mcp.config import Config
from tim_mcp.tools.composition import (
    _load_compositions,
    generate_module_composition_impl,
)
from tim_mcp.types import GenerateModuleCompositionRequest


@pytest.fixture
def config():
    """Create a test configuration."""
    return Config()


async def _run(config, service_or_pattern, environment=None):
    request = GenerateModuleCompositionRequest(
        service_or_pattern=service_or_pattern, environment=environment
    )
    return await generate_module_composition_impl(request, config)


@pytest.mark.asyncio
async def test_service_keyword_matches_composition(config):
    """A plain service keyword returns the expected composition."""
    response = await _run(config, "openshift")

    assert response.matched is True
    assert response.composition is not None
    assert response.composition.composition_name == "openshift"


@pytest.mark.asyncio
async def test_exact_composition_name_short_circuits(config):
    """Passing the exact composition name returns that composition directly."""
    response = await _run(config, "postgresql")

    assert response.matched is True
    assert response.composition.composition_name == "postgresql"
    assert response.alternatives == []


@pytest.mark.asyncio
async def test_multi_word_query_matches(config):
    """Multi-word queries with separators are tokenized and matched."""
    response = await _run(config, "event streams")

    assert response.matched is True
    assert response.composition.composition_name == "event-streams"


@pytest.mark.asyncio
async def test_modules_are_enriched_with_versions(config):
    """Recommended modules are enriched with resolved version and source."""
    response = await _run(config, "watsonx")

    modules = response.composition.recommended_modules
    assert len(modules) > 0
    for module in modules:
        # source mirrors the base id, and version is resolved from the index
        assert module.source == module.id
        assert module.version is not None
        assert module.registry_url is not None
        assert module.version in module.registry_url


@pytest.mark.asyncio
async def test_deployment_order_matches_module_instances(config):
    """Every deployment_order entry corresponds to a recommended module instance."""
    response = await _run(config, "openshift")
    composition = response.composition

    instance_names = {m.instance_name for m in composition.recommended_modules}
    assert set(composition.deployment_order) == instance_names


@pytest.mark.asyncio
async def test_connections_reference_known_instances(config):
    """Connections only reference modules that are part of the composition."""
    response = await _run(config, "openshift")
    composition = response.composition

    instance_names = {m.instance_name for m in composition.recommended_modules}
    for connection in composition.connections:
        assert connection.source_module in instance_names
        assert connection.target_module in instance_names


@pytest.mark.asyncio
async def test_no_match_returns_available_compositions(config):
    """An unmatched query returns the full catalog for the caller to choose from."""
    response = await _run(config, "totally-unknown-service-xyz")

    assert response.matched is False
    assert response.composition is None
    assert len(response.available_compositions) == len(_load_compositions())
    assert response.message is not None


@pytest.mark.asyncio
async def test_environment_bias_is_applied(config):
    """A production environment bias keeps the production composition."""
    response = await _run(config, "openshift", environment="production")
    assert response.matched is True
    assert response.composition.environment == "production"


@pytest.mark.asyncio
async def test_unknown_environment_is_ignored(config):
    """An unknown environment does not break matching."""
    response = await _run(config, "postgresql", environment="staging")
    assert response.matched is True
    assert response.composition.composition_name == "postgresql"


@pytest.mark.asyncio
async def test_all_compositions_are_well_formed(config):
    """Every composition in the catalog builds and enriches without error."""
    for raw in _load_compositions():
        response = await _run(config, raw["name"])
        assert response.matched is True
        composition = response.composition
        assert composition.recommended_modules
        assert composition.deployment_order
        assert composition.prerequisites


@pytest.mark.asyncio
async def test_reference_solution_present_and_hinted(config):
    """Every composition is anchored to a DA solution with a runnable fetch hint."""
    for raw in _load_compositions():
        response = await _run(config, raw["name"])
        ref = response.composition.reference_solution
        assert ref is not None, f"{raw['name']} missing reference_solution"
        assert ref.module_id and ref.solution_path
        assert ref.source_url.startswith("https://github.com/")
        # fetch_hint should be a runnable get_content call pinned to a version
        assert ref.fetch_hint.startswith("get_content(")
        assert ref.solution_path in ref.fetch_hint


@pytest.mark.asyncio
async def test_module_roles_are_valid_and_have_core(config):
    """Every module has a valid role and each composition has at least one core module."""
    valid = {"core", "prerequisite", "optional"}
    for raw in _load_compositions():
        response = await _run(config, raw["name"])
        modules = response.composition.recommended_modules
        roles = {m.role for m in modules}
        assert roles <= valid, f"{raw['name']} has invalid role(s): {roles - valid}"
        assert "core" in roles, f"{raw['name']} has no core module"


@pytest.mark.asyncio
async def test_reference_solution_module_is_in_the_stack(config):
    """The anchor DA's module should also appear among the composition's modules."""
    for raw in _load_compositions():
        response = await _run(config, raw["name"])
        composition = response.composition
        module_ids = {m.id for m in composition.recommended_modules}
        assert composition.reference_solution.module_id in module_ids

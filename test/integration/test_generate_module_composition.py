"""
Tests for the generate_module_composition tool.

The tool assembles a composition live by calling search_modules and
get_module_details. These tests mock those live helpers so the assembly logic
(service detection, connection inference, DA gating, JSON shape) runs offline.
"""

from types import SimpleNamespace

import pytest

from tim_mcp.config import Config
from tim_mcp.exceptions import TIMError
from tim_mcp.tools import composition as comp
from tim_mcp.types import GenerateModuleCompositionRequest

# Fake module interfaces keyed by service instance name.
_FAKE = {
    "resource_group": {
        "id": "terraform-ibm-modules/resource-group/ibm",
        "version": "1.6.1",
        "inputs": {"resource_group_name"},
        "outputs": {"resource_group_id"},
    },
    "kms": {
        "id": "terraform-ibm-modules/kms-all-inclusive/ibm",
        "version": "5.6.5",
        "inputs": {"resource_group_id", "region"},
        "outputs": {"key_crn", "kms_guid"},
    },
    "vpc": {
        "id": "terraform-ibm-modules/landing-zone-vpc/ibm",
        "version": "9.2.1",
        "inputs": {"resource_group_id", "region"},
        "outputs": {"vpc_id", "subnet_detail_map"},
    },
    "cos": {
        "id": "terraform-ibm-modules/cos/ibm",
        "version": "10.17.5",
        "inputs": {"resource_group_id", "kms_key_crn"},
        "outputs": {"cos_instance_id", "cos_instance_crn"},
    },
    "openshift": {
        "id": "terraform-ibm-modules/base-ocp-vpc/ibm",
        "version": "3.90.4",
        "inputs": {"resource_group_id", "vpc_id", "existing_cos_id", "region"},
        "outputs": {"cluster_id"},
    },
    "postgresql": {
        "id": "terraform-ibm-modules/icd-postgresql/ibm",
        "version": "4.15.3",
        "inputs": {"resource_group_id", "kms_key_crn"},
        "outputs": {"id"},
    },
}


@pytest.fixture
def config():
    return Config()


@pytest.fixture(autouse=True)
def mock_live_calls(monkeypatch):
    """Mock the live search/details helpers with the fake registry above."""

    async def fake_search_best(svc, config):
        entry = _FAKE.get(svc.instance)
        if entry is None:
            return None
        name = entry["id"].split("/")[1]
        return SimpleNamespace(
            id=entry["id"],
            version=entry["version"],
            name=name,
            description=f"{name} module description.",
            source_url=f"https://github.com/terraform-ibm-modules/terraform-ibm-{name}",
        )

    async def fake_fetch_interface(module_id, version, config):
        for entry in _FAKE.values():
            if entry["id"] == module_id:
                return entry["inputs"], entry["outputs"]
        return set(), set()

    monkeypatch.setattr(comp, "_search_best", fake_search_best)
    monkeypatch.setattr(comp, "_fetch_interface", fake_fetch_interface)


async def _run(config, prompt):
    return await comp.generate_module_composition_impl(
        GenerateModuleCompositionRequest(prompt=prompt), config
    )


@pytest.mark.asyncio
async def test_returns_composition_json_shape(config):
    c = await _run(config, "gimme an openshift composition with kms and cos")
    assert c.composition_name == "openshift-composition"
    assert {m.instance_name for m in c.recommended_modules} >= {
        "resource_group",
        "kms",
        "vpc",
        "cos",
        "openshift",
    }
    assert c.prerequisites and c.deployment_order


@pytest.mark.asyncio
async def test_modules_resolved_with_live_versions(config):
    c = await _run(config, "openshift with kms and cos")
    for m in c.recommended_modules:
        assert m.version  # came from (mocked) search_modules
        assert m.source == m.id
        assert m.version in m.registry_url


@pytest.mark.asyncio
async def test_resource_group_wired_everywhere(config):
    c = await _run(config, "openshift with kms and cos")
    rg_targets = {
        cn.target_module
        for cn in c.connections
        if cn.source_module == "resource_group"
        and cn.source_output == "resource_group_id"
    }
    assert {"kms", "vpc", "cos", "openshift"} <= rg_targets


@pytest.mark.asyncio
async def test_exact_and_alias_connections_inferred(config):
    c = await _run(config, "openshift with kms and cos")
    pairs = {
        (cn.source_module, cn.source_output, cn.target_module, cn.target_input)
        for cn in c.connections
    }
    # exact name match: vpc_id -> openshift.vpc_id
    assert ("vpc", "vpc_id", "openshift", "vpc_id") in pairs
    # encryption alias: kms key_crn -> cos.kms_key_crn
    assert ("kms", "key_crn", "cos", "kms_key_crn") in pairs


@pytest.mark.asyncio
async def test_cluster_pulls_in_vpc(config):
    c = await _run(config, "openshift with kms")
    assert "vpc" in c.deployment_order


@pytest.mark.asyncio
async def test_deployment_order_is_dependency_ordered(config):
    c = await _run(config, "openshift with kms and cos")
    order = c.deployment_order
    assert order.index("resource_group") == 0
    assert order.index("kms") < order.index("openshift")
    assert order.index("vpc") < order.index("openshift")


@pytest.mark.asyncio
async def test_no_da_means_no_da_grounding(config):
    c = await _run(config, "postgresql with kms")
    assert c.da_grounded is False
    assert all(cn.origin == "inferred" for cn in c.connections)


@pytest.mark.asyncio
async def test_da_prompt_sets_reference_solution(config, monkeypatch):
    async def fake_solution(module_id, config):
        return "solutions/fully-configurable"

    monkeypatch.setattr(comp, "_resolve_da_solution", fake_solution)
    c = await _run(config, "postgresql composition with a DA")
    # DA grounding => a reference_solution pointer; connections stay inferred
    assert c.da_grounded is True
    assert c.reference_solution is not None
    assert c.reference_solution.solution_path == "solutions/fully-configurable"
    assert all(cn.origin == "inferred" for cn in c.connections)


@pytest.mark.asyncio
async def test_da_substring_does_not_trigger(config, monkeypatch):
    called = {"da": False}

    async def fake_solution(module_id, config):
        called["da"] = True
        return "solutions/x"

    monkeypatch.setattr(comp, "_resolve_da_solution", fake_solution)
    c = await _run(config, "a postgresql database for my data platform")
    assert called["da"] is False
    assert c.da_grounded is False
    assert c.reference_solution is None


@pytest.mark.asyncio
async def test_modules_have_role_and_purpose(config):
    c = await _run(config, "openshift with kms and cos")
    by_instance = {m.instance_name: m for m in c.recommended_modules}
    assert by_instance["resource_group"].role == "foundation"
    assert by_instance["openshift"].role == "workload"
    assert by_instance["kms"].role == "support"
    assert all(m.purpose for m in c.recommended_modules)
    assert c.description


@pytest.mark.asyncio
async def test_no_recognized_service_is_flagged(config):
    """A prompt with no mapped service (only the RG foundation) is flagged."""
    c = await _run(config, "help me build a cool web application")
    assert [m.instance_name for m in c.recommended_modules] == ["resource_group"]
    assert any("No IBM Cloud services were recognised" in n for n in c.notes)


@pytest.mark.asyncio
async def test_unmapped_workload_is_flagged(config):
    """A recognised support service but an unmapped workload (Db2) is flagged."""
    c = await _run(config, "set up a Db2 database with kms encryption")
    instances = {m.instance_name for m in c.recommended_modules}
    assert instances == {"resource_group", "kms"}  # Db2 isn't mapped
    assert any("No primary workload/service was recognised" in n for n in c.notes)


@pytest.mark.asyncio
async def test_recognised_workload_has_no_unmapped_note(config):
    """A fully-recognised request doesn't get the unmapped/unrecognised notes."""
    c = await _run(config, "postgresql with kms")
    assert not any("recognised" in n for n in c.notes)


@pytest.mark.asyncio
async def test_unresolvable_request_raises(config, monkeypatch):
    async def none_search(svc, config):
        return None

    monkeypatch.setattr(comp, "_search_best", none_search)
    with pytest.raises(TIMError):
        await _run(config, "openshift with kms")

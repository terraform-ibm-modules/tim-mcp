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


def _inputs(*names, required=(), types=None):
    """Build the {name: metadata} interface shape returned by _fetch_interface."""
    types = types or {}
    return {
        n: {"type": types.get(n, "string"), "required": n in required} for n in names
    }


# Fake module interfaces keyed by service instance name.
_FAKE = {
    "resource_group": {
        "id": "terraform-ibm-modules/resource-group/ibm",
        "version": "1.6.1",
        "inputs": _inputs("resource_group_name"),
        "outputs": {"resource_group_id"},
    },
    "kms": {
        "id": "terraform-ibm-modules/kms-all-inclusive/ibm",
        "version": "5.6.5",
        "inputs": _inputs("resource_group_id", "region"),
        "outputs": {"key_crn", "kms_guid"},
    },
    "vpc": {
        "id": "terraform-ibm-modules/landing-zone-vpc/ibm",
        "version": "9.2.1",
        "inputs": _inputs("resource_group_id", "region"),
        "outputs": {"vpc_id", "subnet_detail_map"},
    },
    "cos": {
        "id": "terraform-ibm-modules/cos/ibm",
        "version": "10.17.5",
        "inputs": _inputs("resource_group_id", "kms_key_crn"),
        # cos re-exports the key CRN it was given — a name-identical output
        # that must not be mistaken for the source of that value.
        "outputs": {
            "cos_instance_id",
            "cos_instance_crn",
            "cos_instance_name",
            "kms_key_crn",
        },
    },
    "openshift": {
        "id": "terraform-ibm-modules/base-ocp-vpc/ibm",
        "version": "3.90.4",
        "inputs": _inputs(
            "resource_group_id",
            "vpc_id",
            "existing_cos_id",
            "region",
            "worker_pools",
            "security_group_id",
            "cluster_name",
            "cos_name",
            "use_existing_cos",
            required=("existing_cos_id",),
            types={
                "use_existing_cos": "bool",
                "worker_pools": (
                    "list(object({ pool_name = string, "
                    "boot_volume_encryption_kms_config = string }))"
                ),
            },
        ),
        "outputs": {"cluster_id"},
        # the real base-ocp-vpc instantiates COS itself for registry storage
        "provisions": ["terraform-ibm-modules/cos/ibm"],
    },
    "secrets_manager": {
        "id": "terraform-ibm-modules/secrets-manager/ibm",
        "version": "2.6.0",
        "inputs": _inputs("resource_group_id", "region"),
        "outputs": {"secrets_manager_crn", "secrets_manager_guid"},
    },
    "cloudant": {
        "id": "terraform-ibm-modules/cloudant/ibm",
        "version": "1.3.0",
        "inputs": _inputs("resource_group_id"),
        "outputs": {"id"},
    },
    "postgresql": {
        "id": "terraform-ibm-modules/icd-postgresql/ibm",
        "version": "4.15.3",
        "inputs": _inputs("resource_group_id", "kms_key_crn"),
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
                return entry["inputs"], entry["outputs"], entry.get("provisions", [])
        return {}, set(), []

    monkeypatch.setattr(comp, "_search_best", fake_search_best)
    monkeypatch.setattr(comp, "_fetch_interface", fake_fetch_interface)


async def _run(config, prompt=None, services=None, include_da=False):
    return await comp.generate_module_composition_impl(
        GenerateModuleCompositionRequest(
            prompt=prompt, services=services, include_da=include_da
        ),
        config,
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


def _by_target(composition, instance, input_name):
    return next(
        (
            cn
            for cn in composition.connections
            if cn.target_module == instance and cn.target_input == input_name
        ),
        None,
    )


@pytest.mark.asyncio
async def test_live_calls_run_in_parallel(config, monkeypatch):
    """
    Searches fan out together, and so do the interface reads — the tool makes
    one round of each rather than one call per module in series.
    """
    import asyncio

    peak = {"search": 0, "interface": 0}
    live = {"search": 0, "interface": 0}

    def _tracked(kind, inner):
        async def wrapper(*args, **kwargs):
            live[kind] += 1
            peak[kind] = max(peak[kind], live[kind])
            try:
                await asyncio.sleep(0.01)
                return await inner(*args, **kwargs)
            finally:
                live[kind] -= 1

        return wrapper

    monkeypatch.setattr(comp, "_search_best", _tracked("search", comp._search_best))
    monkeypatch.setattr(
        comp, "_fetch_interface", _tracked("interface", comp._fetch_interface)
    )

    c = await _run(config, "openshift with kms and cos")
    assert len(c.recommended_modules) == 5
    assert peak["search"] == 5
    assert peak["interface"] == 5


def _prereqs(composition):
    return {p.name: p for p in composition.prerequisites}


@pytest.mark.asyncio
async def test_prerequisites_are_derived_from_the_modules(config):
    """Only values the resolved modules actually take, with real requiredness."""
    c = await _run(config, "openshift with kms and cos")
    p = _prereqs(c)
    assert p["ibmcloud_api_key"].required  # provider-level, always there
    assert "region" in p
    # nothing in the fixture marks region required, so it must not claim to be
    assert p["region"].required is False
    assert "resource_group_name" in p


@pytest.mark.asyncio
async def test_prerequisites_omit_values_no_module_takes(config):
    """A composition whose modules take no region gets no region prerequisite."""
    c = await _run(config, services=["cloudant"])
    p = _prereqs(c)
    assert "region" not in p
    assert "ibmcloud_api_key" in p


@pytest.mark.asyncio
async def test_required_unwired_input_becomes_a_prerequisite(config):
    """
    With no cos module, the cluster's required existing_cos_id can't be wired,
    so the consumer has to supply it.
    """
    c = await _run(config, services=["openshift", "kms"])
    p = _prereqs(c)
    assert "openshift.existing_cos_id" in p
    assert p["openshift.existing_cos_id"].required is True


@pytest.mark.asyncio
async def test_use_existing_inputs_are_offered_as_optional(config, monkeypatch):
    """Optional existing_* inputs are reuse options, not requirements."""
    monkeypatch.setitem(
        _FAKE["vpc"]["inputs"],
        "existing_dns_instance_id",
        {
            "type": "string",
            "required": False,
            "description": "An existing DNS instance.",
        },
    )
    c = await _run(config, "openshift with kms and cos")
    p = _prereqs(c)
    assert "vpc.existing_dns_instance_id" in p
    assert p["vpc.existing_dns_instance_id"].required is False


@pytest.mark.asyncio
async def test_prerequisites_fall_back_when_interfaces_cannot_be_read(
    config, monkeypatch
):
    """Nothing to derive from means the standard set, not an empty list."""

    async def boom(module_id, version, config):
        raise RuntimeError("registry down")

    monkeypatch.setattr(comp, "_fetch_interface", boom)
    c = await _run(config, "openshift with kms and cos")
    assert {p.name for p in c.prerequisites} == {
        "ibmcloud_api_key",
        "region",
        "resource_group_name",
        "prefix",
    }


@pytest.mark.asyncio
async def test_declared_dependencies_are_reported(config):
    """A module's declared whole-module dependencies reach the output."""
    c = await _run(config, "openshift with kms and cos")
    by_instance = {m.instance_name: m for m in c.recommended_modules}
    assert by_instance["openshift"].provisions == ["terraform-ibm-modules/cos/ibm"]
    assert by_instance["cos"].provisions == []


@pytest.mark.asyncio
async def test_duplicate_provisioning_is_flagged_with_its_toggle(config):
    """
    The cluster creates its own COS unless told otherwise, so wiring
    existing_cos_id isn't enough — the note has to name the flag too.
    """
    c = await _run(config, "openshift with kms and cos")
    note = next(n for n in c.notes if "instantiates" in n)
    assert "terraform-ibm-modules/cos/ibm" in note
    assert "existing_cos_id is wired" in note
    assert "use_existing_cos is true" in note


@pytest.mark.asyncio
async def test_no_duplicate_note_when_the_module_is_not_in_the_composition(config):
    """Provisioning something the composition doesn't deploy isn't a clash."""
    c = await _run(config, services=["openshift", "kms"])
    assert not any("instantiates" in n for n in c.notes)


def test_utility_submodules_are_not_reported_as_provisioned():
    """crn-parser and friends are plumbing, not architecture."""
    provisions = comp._provisioned_modules(
        [
            {
                "source": "terraform-ibm-modules/common-utilities/ibm//modules/crn-parser"
            },
            {"source": "terraform-ibm-modules/cbr/ibm//modules/cbr-rule-module"},
            {"source": "terraform-ibm-modules/cos/ibm"},
            {"source": "terraform-ibm-modules/cos/ibm"},  # deduped
            {"source": ""},
        ]
    )
    assert provisions == ["terraform-ibm-modules/cos/ibm"]


@pytest.mark.asyncio
async def test_renamed_link_wired_by_kind(config):
    """existing_cos_id wires to the cos module's *_id output, and is marked."""
    c = await _run(config, "openshift with kms and cos")
    cn = _by_target(c, "openshift", "existing_cos_id")
    assert cn is not None
    assert (cn.source_module, cn.source_output) == ("cos", "cos_instance_id")
    assert cn.origin == "inferred-kind"


@pytest.mark.asyncio
async def test_exact_match_keeps_high_confidence_origin(config):
    """Tier 0 wins where it applies and stays plain 'inferred'."""
    c = await _run(config, "openshift with kms and cos")
    cn = _by_target(c, "openshift", "vpc_id")
    assert cn is not None and cn.origin == "inferred"


@pytest.mark.asyncio
async def test_kind_match_does_not_drift_to_unrelated_id(config):
    """
    security_group_id names no module in the composition, so it must stay
    unwired rather than grabbing some other module's *_id output.
    """
    c = await _run(config, "openshift with kms and cos")
    assert _by_target(c, "openshift", "security_group_id") is None
    assert any("security_group_id" in n for n in c.notes)


@pytest.mark.asyncio
async def test_self_reference_is_not_wired(config):
    """cluster_name can't wire from the cluster module consuming it."""
    c = await _run(config, "openshift with kms and cos")
    assert _by_target(c, "openshift", "cluster_name") is None


@pytest.mark.asyncio
async def test_ambiguous_output_is_flagged_not_guessed(config, monkeypatch):
    """Two equally-plausible *_id outputs: refuse to wire, and say so."""
    monkeypatch.setitem(
        _FAKE["cos"], "outputs", {"primary_id", "secondary_id", "cos_instance_crn"}
    )
    c = await _run(config, "openshift with kms and cos")
    assert _by_target(c, "openshift", "existing_cos_id") is None
    assert any(
        "existing_cos_id" in n and "primary_id, secondary_id" in n for n in c.notes
    )


@pytest.mark.asyncio
async def test_unwired_input_is_reported_with_reason(config):
    """A required input with no source module is named in the notes."""
    c = await _run(config, "openshift with kms")
    note = next(n for n in c.notes if n.startswith("openshift:"))
    assert "existing_cos_id (required)" in note
    assert "no 'cos' module in this composition" in note


@pytest.mark.asyncio
async def test_nested_object_input_is_flagged(config):
    """worker_pools carries KMS config inside a list(object) — detect and note."""
    c = await _run(config, "openshift with kms and cos")
    assert any("worker_pools" in n and "nested" in n for n in c.notes)


@pytest.mark.asyncio
async def test_vpc_subnets_wires_to_the_subnet_detail_map(config, monkeypatch):
    """
    vpc_subnets takes map(list(object({id, zone, cidr_block}))) — the shape of
    subnet_detail_map, and the wiring shipped DAs use — so it must not be left
    ambiguous against the VPC's other subnet outputs.
    """
    monkeypatch.setitem(
        _FAKE["vpc"],
        "outputs",
        {
            "vpc_id",
            "subnet_detail_map",
            "subnet_detail_list",
            "subnet_ids",
            "subnet_zone_list",
        },
    )
    monkeypatch.setitem(
        _FAKE["openshift"]["inputs"],
        "vpc_subnets",
        {"type": "map(list(object({})))", "required": True},
    )
    c = await _run(config, "openshift with kms and cos")
    cn = _by_target(c, "openshift", "vpc_subnets")
    assert cn is not None
    assert (cn.source_module, cn.source_output) == ("vpc", "subnet_detail_map")
    assert cn.origin == "inferred-alias"


@pytest.mark.asyncio
async def test_re_exported_output_is_not_treated_as_the_source(config):
    """
    cos re-exports kms_key_crn under the same name. The key comes from kms —
    wiring it from cos would invent a dependency on the wrong module.
    """
    c = await _run(config, "postgresql with kms and cos")
    cn = _by_target(c, "postgresql", "kms_key_crn")
    assert cn is not None
    assert (cn.source_module, cn.source_output) == ("kms", "key_crn")
    assert cn.origin == "inferred-alias"


@pytest.mark.asyncio
async def test_pass_through_output_is_not_treated_as_the_source(config, monkeypatch):
    """
    With no resource_group module, cos's echoed resource_group_id must not
    become vpc's source for it — cos consumes that value, it doesn't own it.
    """
    monkeypatch.delitem(_FAKE, "resource_group")  # unresolvable via search
    monkeypatch.setitem(
        _FAKE["cos"],
        "outputs",
        {"cos_instance_id", "cos_instance_crn", "resource_group_id"},
    )
    c = await _run(config, services=["cos", "vpc"])
    assert _by_target(c, "vpc", "resource_group_id") is None
    assert any("resource_group_id" in n and "no 'group' module" in n for n in c.notes)


@pytest.mark.asyncio
async def test_re_export_not_wired_when_the_owning_kind_is_absent(config):
    """With no kms module, cos's same-named output is still not the source."""
    c = await _run(config, services=["postgresql", "cos"])
    assert _by_target(c, "postgresql", "kms_key_crn") is None
    assert any("kms_key_crn" in n and "no 'kms' module" in n for n in c.notes)


@pytest.mark.asyncio
async def test_secrets_manager_is_not_a_kms_source(config):
    """Secrets Manager consumes key CRNs, it doesn't produce them."""
    c = await _run(config, services=["postgresql", "secrets_manager"])
    assert _by_target(c, "postgresql", "kms_key_crn") is None


@pytest.mark.asyncio
async def test_order_follows_the_connection_graph(config, monkeypatch):
    """
    vpc consuming a COS id must put cos first, even though cos sorts after vpc
    by static service priority.
    """
    monkeypatch.setitem(
        _FAKE["vpc"]["inputs"],
        "existing_cos_id",
        {"type": "string", "required": False},
    )
    c = await _run(config, "openshift with kms and cos")
    order = c.deployment_order
    assert order.index("cos") < order.index("vpc")
    # and the link the old priority order could not express is now wired
    cn = _by_target(c, "vpc", "existing_cos_id")
    assert cn is not None and cn.source_module == "cos"


@pytest.mark.asyncio
async def test_order_falls_back_to_priority_on_a_cycle(config, monkeypatch):
    """Mutually-dependent modules can't be ordered — say so, don't hang."""
    monkeypatch.setitem(
        _FAKE["vpc"]["inputs"],
        "existing_cos_id",
        {"type": "string", "required": False},
    )
    monkeypatch.setitem(
        _FAKE["cos"]["inputs"], "vpc_id", {"type": "string", "required": False}
    )
    c = await _run(config, "openshift with kms and cos")
    assert set(c.deployment_order) == {
        "resource_group",
        "kms",
        "vpc",
        "cos",
        "openshift",
    }
    assert c.deployment_order.index("vpc") < c.deployment_order.index("cos")  # priority
    assert any("Circular references" in n and "cos" in n for n in c.notes)


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
    assert all(cn.origin.startswith("inferred") for cn in c.connections)


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
    assert all(cn.origin.startswith("inferred") for cn in c.connections)


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
    """A support service but a workload in no catalog (Snowflake) is flagged."""
    c = await _run(config, "set up a Snowflake database with kms encryption")
    instances = {m.instance_name for m in c.recommended_modules}
    assert instances == {"resource_group", "kms"}  # Snowflake isn't a TIM module
    assert any("No primary workload/service was recognised" in n for n in c.notes)


def test_index_recognises_a_service_the_keyword_map_lacks():
    """Db2 and Elasticsearch are in no keyword entry — the index supplies them."""
    assert "db2_cloud" in [
        s.instance for s in comp._detect_services("set up a Db2 database")
    ]
    assert "icd_elasticsearch" in [
        s.instance for s in comp._detect_services("elasticsearch with cos backups")
    ]


def test_index_ignores_words_that_merely_appear_in_module_names():
    """
    "terraform", "app" and "secure" each occur in a module name, but none of
    them names a service — matching on them would fill every composition with
    terraform-enterprise, app-configuration and security-group.
    """
    picked = [
        s.instance for s in comp._detect_services("terraform modules for a secure app")
    ]
    assert picked == ["resource_group"]


def test_index_prefers_the_more_specific_module():
    """ "watsonx orchestrate" beats the broader "watsonx" keyword..."""
    picked = [
        s.instance for s in comp._detect_services("watsonx orchestrate for my team")
    ]
    assert "watsonx_orchestrate" in picked
    assert "watsonx_ai" not in picked
    # ...unless watsonx.ai is asked for by name too
    both = [
        s.instance for s in comp._detect_services("watsonx ai and watsonx orchestrate")
    ]
    assert {"watsonx_ai", "watsonx_orchestrate"} <= set(both)


def test_curated_keyword_wins_over_the_index():
    """ "object storage" is COS, not the module literally named *-file-storage."""
    picked = [s.instance for s in comp._detect_services("i need object storage")]
    assert "cos" in picked
    assert "vpc_file_storage" not in picked


def test_index_service_priority_comes_from_its_category():
    """An index-derived service is placed by category, not lumped in as a workload."""
    picked = {
        s.instance: s for s in comp._detect_services("event notifications please")
    }
    assert picked["event_notifications"].priority == 4  # observability -> support
    assert comp._role_for(picked["event_notifications"].priority) == "support"


@pytest.mark.asyncio
async def test_services_input_resolves_via_the_index(config):
    """An explicit service the keyword map doesn't know still resolves."""
    c = await _run(config, services=["cloudant"])
    by_instance = {m.instance_name: m for m in c.recommended_modules}
    assert "cloudant" in by_instance
    assert by_instance["cloudant"].id == "terraform-ibm-modules/cloudant/ibm"


@pytest.mark.asyncio
async def test_recognised_workload_has_no_unmapped_note(config):
    """A fully-recognised request doesn't get the unmapped/unrecognised notes."""
    c = await _run(config, "postgresql with kms")
    assert not any("recognised" in n for n in c.notes)


@pytest.mark.asyncio
async def test_services_input_bypasses_prompt_parsing(config):
    """An explicit services list is resolved directly (no prompt needed)."""
    c = await _run(config, services=["openshift", "kms", "cos"])
    instances = {m.instance_name for m in c.recommended_modules}
    # known terms map to known services; cluster still pulls in a VPC
    assert {"resource_group", "openshift", "kms", "cos", "vpc"} <= instances


@pytest.mark.asyncio
async def test_services_input_skips_unrecognized_notes(config):
    """The keyword-path 'nothing recognised' notes don't fire for explicit services."""
    c = await _run(config, services=["kms"])
    assert not any("recognised" in n for n in c.notes)


@pytest.mark.asyncio
async def test_include_da_flag_sets_reference_solution(config, monkeypatch):
    async def fake_solution(module, config):
        return "solutions/fully-configurable"

    monkeypatch.setattr(comp, "_resolve_da_solution", fake_solution)
    c = await _run(config, services=["postgresql", "kms"], include_da=True)
    assert c.da_grounded is True
    assert c.reference_solution is not None


def test_request_requires_services_or_prompt():
    """The request model rejects empty input."""
    with pytest.raises(ValueError):
        GenerateModuleCompositionRequest()


@pytest.mark.asyncio
async def test_unresolvable_request_raises(config, monkeypatch):
    async def none_search(svc, config):
        return None

    monkeypatch.setattr(comp, "_search_best", none_search)
    with pytest.raises(TIMError):
        await _run(config, prompt="openshift with kms")

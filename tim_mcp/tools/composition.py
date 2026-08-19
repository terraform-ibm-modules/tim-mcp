"""
Module composition tool for TIM-MCP.

``generate_module_composition`` takes a natural-language prompt (e.g.
"gimme an openshift composition with kms and cos") and assembles a composition
by calling the *other* TIM-MCP tools live:

- ``search_modules`` resolves each service to a real module ID + latest version
- ``get_module_details`` reads each module's real inputs/outputs
- connections are inferred from those interfaces (output name → input name)
- when the prompt mentions a DA, a ``reference_solution`` pointer to the module's
  deployable-architecture ``solutions/`` directory is added (the authoritative
  wiring the agent can fetch with ``get_content``)

Nothing is hardcoded: module IDs, versions, and wiring are discovered at request
time. The only baked-in knowledge is a lightweight map of service keywords →
search terms used to classify the prompt.
"""

import re

from ..clients.terraform_client import TerraformClient
from ..config import Config
from ..context import get_cache, get_rate_limiter
from ..exceptions import TIMError
from ..logging import get_logger
from ..types import (
    CompositionPrerequisite,
    GenerateModuleCompositionRequest,
    ModuleComposition,
    ModuleConnection,
    RecommendedModule,
    ReferenceSolution,
)
from ..utils.module_id import parse_module_id

logger = get_logger(__name__)


# Service registry: keyword classification + the search term used to find the
# module. NOT module IDs/versions -- those come from search_modules at runtime.
# priority drives deployment order (lower = earlier).
class _Service:
    __slots__ = (
        "key",
        "display",
        "instance",
        "query",
        "keywords",
        "name_match",
        "priority",
    )

    def __init__(self, key, display, instance, query, keywords, name_match, priority):
        self.key = key
        self.display = display
        self.instance = instance
        self.query = query
        self.keywords = keywords
        self.name_match = name_match
        self.priority = priority


_SERVICES: list[_Service] = [
    _Service(
        "resource_group",
        "Resource group",
        "resource_group",
        "resource group",
        ["resource group", "resource-group", " rg "],
        ["resource-group"],
        0,
    ),
    _Service(
        "kms",
        "Key management (KMS)",
        "kms",
        "kms",
        ["kms", "key protect", "key management", "hpcs", "byok", "encryption"],
        ["kms-all-inclusive", "key-protect", "kms"],
        1,
    ),
    _Service(
        "secrets_manager",
        "Secrets Manager",
        "secrets_manager",
        "secrets manager",
        ["secrets manager", "secrets-manager"],
        ["secrets-manager"],
        1,
    ),
    _Service(
        "vpc",
        "VPC network",
        "vpc",
        "vpc",
        ["vpc", "network", "subnet", "landing zone"],
        ["landing-zone-vpc", "vpc"],
        2,
    ),
    _Service(
        "cos",
        "Object storage (COS)",
        "cos",
        "object storage",
        ["cos", "object storage", "bucket"],
        ["cos"],
        3,
    ),
    _Service(
        "cloud_logs",
        "Cloud Logs",
        "cloud_logs",
        "cloud logs",
        ["cloud logs", "logging", "log analysis", "observability"],
        ["cloud-logs"],
        4,
    ),
    _Service(
        "cloud_monitoring",
        "Cloud Monitoring",
        "cloud_monitoring",
        "cloud monitoring",
        ["cloud monitoring", "monitoring", "metrics"],
        ["cloud-monitoring"],
        4,
    ),
    _Service(
        "openshift",
        "OpenShift cluster",
        "openshift",
        "openshift",
        ["openshift", "ocp", "roks"],
        ["base-ocp-vpc", "ocp"],
        5,
    ),
    _Service(
        "iks",
        "Kubernetes (IKS) cluster",
        "iks",
        "iks",
        ["iks", "kubernetes", "k8s"],
        ["base-iks-vpc", "iks"],
        5,
    ),
    _Service(
        "postgresql",
        "PostgreSQL database",
        "postgresql",
        "postgresql",
        ["postgresql", "postgres"],
        ["icd-postgresql"],
        5,
    ),
    _Service("mysql", "MySQL database", "mysql", "mysql", ["mysql"], ["icd-mysql"], 5),
    _Service("redis", "Redis", "redis", "redis", ["redis"], ["icd-redis"], 5),
    _Service(
        "mongodb",
        "MongoDB",
        "mongodb",
        "mongodb",
        ["mongodb", "mongo"],
        ["icd-mongodb"],
        5,
    ),
    _Service(
        "watsonx_ai",
        "watsonx.ai",
        "watsonx_ai",
        "watsonx ai",
        ["watsonx", "genai", "generative ai"],
        ["watsonx-ai"],
        5,
    ),
    _Service(
        "event_streams",
        "Event Streams (Kafka)",
        "event_streams",
        "event streams",
        ["event streams", "event-streams", "kafka", "messaging"],
        ["event-streams"],
        5,
    ),
]

# Workload services imply a VPC network foundation.
_NEEDS_VPC = {"openshift", "iks"}

# Input names that are top-level prerequisites, not inter-module connections.
_PREREQ_INPUTS = {
    "region",
    "prefix",
    "name",
    "resource_group_name",
    "resource_tags",
    "access_tags",
    "tags",
    "ibmcloud_api_key",
}


def _mentions_da(prompt: str) -> bool:
    """True only when the prompt explicitly references a Deployable Architecture."""
    p = prompt.lower()
    if "deployable architecture" in p or "solutions/" in p:
        return True
    return re.search(r"\bda\b", p) is not None


def _detect_services(prompt: str) -> list[_Service]:
    """Classify which services the prompt asks for (deduped, deployment-ordered)."""
    p = f" {prompt.lower()} "
    picked: dict[str, _Service] = {}
    for svc in _SERVICES:
        if svc.key in picked:
            continue
        if any(kw in p for kw in svc.keywords):
            picked[svc.key] = svc

    # Always include a resource group foundation.
    if "resource_group" not in picked:
        picked["resource_group"] = next(
            s for s in _SERVICES if s.key == "resource_group"
        )
    # Cluster workloads need a VPC.
    if _NEEDS_VPC & set(picked) and "vpc" not in picked:
        picked["vpc"] = next(s for s in _SERVICES if s.key == "vpc")

    return sorted(picked.values(), key=lambda s: (s.priority, s.key))


def _is_connectable(input_name: str) -> bool:
    """Only wire inputs that look like a cross-module resource reference."""
    if input_name in _PREREQ_INPUTS:
        return False
    return bool(
        re.search(r"_(id|ids|crn|crns|guid|name)$", input_name)
    ) or input_name in {"vpc_subnets"}


# --- Live tool calls (isolated so tests can mock them) ---------------------


async def _search_best(svc: _Service, config: Config):
    """Resolve a service to its best-matching module via search_modules."""
    from ..types import ModuleSearchRequest
    from .search import search_modules_impl

    resp = await search_modules_impl(
        ModuleSearchRequest(query=svc.query, limit=5), config
    )
    if not resp.modules:
        return None
    lowered = [(m, m.name.lower()) for m in resp.modules]
    # 1. Exact name match, honouring name_match preference order.
    for pref in svc.name_match:
        for m, name in lowered:
            if name == pref:
                return m
    # 2. Substring match — prefer the shortest (closest) name to avoid pulling in
    #    a longer variant (e.g. 'secrets-manager-secret-group' for 'secrets-manager').
    candidates = [
        (m, name) for m, name in lowered if any(nm in name for nm in svc.name_match)
    ]
    if candidates:
        return min(candidates, key=lambda t: len(t[1]))[0]
    # 3. Fallback: top (most-downloaded) result.
    return resp.modules[0]


async def _fetch_interface(
    module_id: str, version: str, config: Config
) -> tuple[set[str], set[str]]:
    """Return (input_names, output_names) for a module via the registry."""
    namespace, name, provider = parse_module_id(module_id)
    async with TerraformClient(
        config, cache=get_cache(), rate_limiter=get_rate_limiter()
    ) as tc:
        data = await tc.get_module_details(namespace, name, provider, version)
    root = data.get("root", {})
    inputs = {i.get("name", "") for i in root.get("inputs", [])}
    outputs = {o.get("name", "") for o in root.get("outputs", [])}
    return inputs, outputs


# Preferred DA solution flavours, in order.
_SOLUTION_PREFERENCE = (
    "fully-configurable",
    "security-enforced",
    "standard",
    "quickstart",
)


async def _resolve_da_solution(module, config: Config) -> str | None:
    """
    Find the module's Deployable Architecture solution path (e.g.
    solutions/fully-configurable) by listing the repo's ``solutions/`` directory.

    We intentionally do NOT try to extract the DA's wiring by parsing HCL: real
    DAs route connections through locals/interpolation that regex cannot follow
    reliably, so the extracted wiring is sparser and less correct than inferring
    from module interfaces. Instead we point the agent at the authoritative DA.

    (list_content deliberately hides ``solutions/``, so we query GitHub directly.)
    """
    from ..clients.github_client import GitHubClient

    source_url = str(getattr(module, "source_url", "") or "")
    async with GitHubClient(
        config, cache=get_cache(), rate_limiter=get_rate_limiter()
    ) as gh:
        repo_info = gh.parse_github_url(source_url)
        if not repo_info:
            return None
        owner, repo = repo_info
        try:
            items = await gh.get_directory_contents(owner, repo, "solutions")
        except Exception as e:  # noqa: BLE001 - DA grounding is best-effort
            logger.warning(
                "Could not list DA solutions", repo=f"{owner}/{repo}", error=str(e)
            )
            return None

    dirs = [it.get("name", "") for it in items if it.get("type") == "dir"]
    if not dirs:
        return None
    for pref in _SOLUTION_PREFERENCE:
        if pref in dirs:
            return f"solutions/{pref}"
    return f"solutions/{dirs[0]}"


# --- Assembly -------------------------------------------------------------


def _infer_connections(modules: list[dict]) -> list[ModuleConnection]:
    """
    Infer connections from module interfaces.

    modules is an ordered list (deployment order) of dicts with keys:
    instance, inputs (set), outputs (set).
    """
    connections: list[ModuleConnection] = []
    for i, target in enumerate(modules):
        for input_name in sorted(target["inputs"]):
            if not _is_connectable(input_name):
                continue
            # Exact output-name match from an earlier module.
            wired = False
            for source in modules[:i]:
                if input_name in source["outputs"]:
                    connections.append(
                        ModuleConnection(
                            source_module=source["instance"],
                            source_output=input_name,
                            target_module=target["instance"],
                            target_input=input_name,
                            origin="inferred",
                        )
                    )
                    wired = True
                    break
            if wired:
                continue
            # Encryption alias: *kms*key*crn input ← a KMS module's CRN output.
            if re.search(r"kms.*key.*crn|kms_key_crn", input_name):
                for source in modules[:i]:
                    if source["instance"] not in {"kms", "secrets_manager"}:
                        continue
                    crn_out = next(
                        (
                            o
                            for o in sorted(source["outputs"])
                            if "crn" in o and "key" in o
                        ),
                        None,
                    ) or next(
                        (o for o in sorted(source["outputs"]) if "crn" in o), None
                    )
                    if crn_out:
                        connections.append(
                            ModuleConnection(
                                source_module=source["instance"],
                                source_output=crn_out,
                                target_module=target["instance"],
                                target_input=input_name,
                                origin="inferred",
                            )
                        )
                        break
    return connections


def _role_for(priority: int) -> str:
    """Classify a module's role from its deployment priority."""
    if priority == 0:
        return "foundation"
    if priority >= 5:
        return "workload"
    return "support"


def _describe(services: list[_Service]) -> str:
    """Build a one-line summary of the composition from its services."""
    workloads = [s.display for s in services if s.priority >= 5]
    supporting = [s.display for s in services if 0 < s.priority < 5]
    lead = ", ".join(workloads) if workloads else "IBM Cloud services"
    if supporting:
        return f"{lead} with {', '.join(supporting)}."
    return f"{lead}."


def _standard_prerequisites() -> list[CompositionPrerequisite]:
    return [
        CompositionPrerequisite(
            name="ibmcloud_api_key",
            type="secret",
            required=True,
            description="IBM Cloud API key for the provider.",
        ),
        CompositionPrerequisite(
            name="region",
            type="string",
            required=True,
            description="IBM Cloud region to deploy into.",
        ),
        CompositionPrerequisite(
            name="resource_group_name",
            type="string",
            required=True,
            description="Resource group to create or reuse.",
        ),
        CompositionPrerequisite(
            name="prefix",
            type="string",
            required=False,
            description="Prefix prepended to resource names.",
        ),
    ]


async def generate_module_composition_impl(
    request: GenerateModuleCompositionRequest, config: Config
) -> ModuleComposition:
    """Assemble a composition live from the registry for the given prompt."""
    services = _detect_services(request.prompt)
    da = _mentions_da(request.prompt)
    notes: list[str] = []

    # 1. Resolve each service to a real module + version via search_modules.
    resolved: list[dict] = []
    for svc in services:
        try:
            module = await _search_best(svc, config)
        except Exception as e:  # noqa: BLE001
            logger.warning("search_modules failed", service=svc.key, error=str(e))
            module = None
        if module is None:
            notes.append(
                f"Could not resolve a module for '{svc.display}' via search_modules."
            )
            continue
        resolved.append({"svc": svc, "module": module, "instance": svc.instance})

    if not resolved:
        raise TIMError(
            "No modules could be resolved for this request. Try naming specific "
            "services (e.g. 'openshift with kms and cos')."
        )

    # 2. Fetch each module's interface (inputs/outputs) via get_module_details.
    for entry in resolved:
        module = entry["module"]
        try:
            inputs, outputs = await _fetch_interface(module.id, module.version, config)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "get_module_details failed", module_id=module.id, error=str(e)
            )
            inputs, outputs = set(), set()
            notes.append(
                f"Could not read the interface for {module.id}; wiring may be incomplete."
            )
        entry["inputs"] = inputs
        entry["outputs"] = outputs

    deployment_order = [e["instance"] for e in resolved]

    # 3. Connections: inferred from interfaces; reference the DA when requested.
    connections: list[ModuleConnection] = []
    # Connections are always inferred from module interfaces (real DAs route
    # their wiring through locals/interpolation that can't be extracted reliably).
    connections = _infer_connections(resolved)

    # When a DA is requested, point the agent at the authoritative DA solution.
    reference_solution: ReferenceSolution | None = None
    if da:
        workload = next(
            (e for e in resolved if e["svc"].priority == 5),
            resolved[-1],
        )
        solution_path = await _resolve_da_solution(workload["module"], config)
        if solution_path:
            repo_url = str(getattr(workload["module"], "source_url", "")).rstrip("/")
            reference_solution = ReferenceSolution(
                module_id=workload["module"].id,
                solution_path=solution_path,
                source_url=f"{repo_url}/tree/main/{solution_path}" if repo_url else "",
            )
            notes.append(
                "DA requested: the connections below are inferred from module interfaces. "
                "The authoritative, tested wiring lives in the deployable architecture "
                f"({workload['module'].id}/{solution_path}) — fetch reference_solution with "
                "get_content to mirror it exactly."
            )
        else:
            notes.append(
                "DA requested but no solution directory was found for the primary module; "
                "connections are inferred from module interfaces."
            )

    # Note encryption inputs we could not wire.
    for e in resolved:
        for inp in e["inputs"]:
            if re.search(r"kms.*key.*crn|kms_key_crn", inp) and not any(
                c.target_module == e["instance"] and c.target_input == inp
                for c in connections
            ):
                notes.append(
                    f"{e['instance']}.{inp} expects a KMS key CRN — wire it from your key "
                    "management module (confirm the exact output with get_module_details)."
                )

    primary = next((e for e in resolved if e["svc"].priority == 5), resolved[-1])
    composition_name = f"{primary['svc'].key}-composition"

    logger.info(
        "Assembled composition",
        prompt=request.prompt,
        modules=len(resolved),
        connections=len(connections),
        da_grounded=reference_solution is not None,
    )

    return ModuleComposition(
        composition_name=composition_name,
        description=_describe([e["svc"] for e in resolved]),
        prompt=request.prompt,
        da_grounded=reference_solution is not None,
        reference_solution=reference_solution,
        recommended_modules=[
            RecommendedModule(
                id=e["module"].id,
                instance_name=e["instance"],
                role=_role_for(e["svc"].priority),
                purpose=(getattr(e["module"], "description", "") or "").strip()
                or f"{e['svc'].display} module.",
                version=e["module"].version,
                source=e["module"].id,
                registry_url=f"https://registry.terraform.io/modules/{e['module'].id}/{e['module'].version}",
            )
            for e in resolved
        ],
        deployment_order=deployment_order,
        connections=connections,
        prerequisites=_standard_prerequisites(),
        notes=notes,
    )

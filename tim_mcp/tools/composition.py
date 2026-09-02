"""
Module composition tool for TIM-MCP.

``generate_module_composition`` takes a natural-language prompt (e.g.
"gimme an openshift composition with kms and cos") and assembles a composition
by calling the *other* TIM-MCP tools live:

- ``search_modules`` resolves each service to a real module ID + latest version
- ``get_module_details`` reads each module's real inputs/outputs
- connections are inferred from those interfaces: an exact output-name match
  first, then a kind-scoped match (``existing_cos_id`` can only wire from the
  module whose kind is ``cos``), then a small alias table for names that don't
  carry their kind (``kms_key_crn``). Anything left unwired is reported in
  ``notes`` rather than guessed at.
- when the prompt mentions a DA, a ``reference_solution`` pointer to the module's
  deployable-architecture ``solutions/`` directory is added (the authoritative
  wiring the agent can fetch with ``get_content``)

Nothing is hardcoded: module IDs, versions, and wiring are discovered at request
time. The only baked-in knowledge is a lightweight map of service keywords →
search terms used to classify the prompt.
"""

import asyncio
import re
from collections import Counter
from functools import lru_cache

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

# Generic words signalling the user wants a primary service/workload. Used only to
# warn when none of our mapped services matched as the workload (e.g. a Db2 request);
# this is intent detection, not a catalog of unsupported services.
_WORKLOAD_INTENT = (
    "database",
    "db",
    "cluster",
    "service",
    "instance",
    "application",
    "app",
    "workload",
    "platform",
)


# --- Index-driven recognition --------------------------------------------
#
# The keyword map above covers the services people ask for most, with curated
# choices behind them (kms -> kms-all-inclusive, vpc -> landing-zone-vpc). It
# can't cover the whole catalog, so anything it doesn't recognise is looked up
# in the bundled module index instead.
#
# The index is a filtered subset, not the full catalog, and its refresh job
# drops modules on transient errors — so it augments the keyword map rather
# than replacing it. A service the keyword map claims always wins.

# Deployment priority per index category; anything else is a workload.
_CATEGORY_PRIORITY = {
    "management": 1,
    "security": 1,
    "networking": 2,
    "storage": 3,
    "observability": 4,
}

# Catalog naming conventions that wrap a product name. Stripping these is what
# lets "postgresql" select icd-postgresql and "db2" select db2-cloud.
#
# Only the full module name and these strippings are ever matched. Matching on
# any old token of a name would let single English words select modules —
# "terraform" would mean terraform-enterprise, "code" code-engine, "container"
# container-registry, "security" security-group — so a partial name has to be
# a product name, not a word that happens to appear in one.
_FAMILY_PREFIXES = ("icd-",)
_FAMILY_SUFFIXES = ("-cloud",)


def _phrase(text: str) -> str:
    """Normalise a name or term to space-separated lowercase tokens."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


@lru_cache(maxsize=1)
def _index_phrases() -> tuple[dict[str, str], dict[str, dict]]:
    """
    Build (phrase -> module name, module name -> index entry) from the index.

    A phrase only survives if it identifies exactly one module: the module's
    full name always does, and so does its name minus a family affix when no
    other module claims that phrase. Anything ambiguous is left out, so
    "watsonx" selects nothing while "watsonx ai" selects one module.
    """
    from .search import load_module_index

    index = load_module_index()
    if not index:
        return {}, {}
    entries = {m["name"]: m for m in index.get("modules", []) if m.get("name")}

    phrases = {_phrase(name): name for name in entries}
    stripped_counts: Counter[str] = Counter()
    stripped_owner: dict[str, str] = {}
    for name in entries:
        stripped = _strip_family_affix(name)
        if stripped:
            stripped_counts[stripped] += 1
            stripped_owner.setdefault(stripped, name)
    for stripped, count in stripped_counts.items():
        if count == 1 and stripped not in phrases:
            phrases[stripped] = stripped_owner[stripped]
    return phrases, entries


def _strip_family_affix(name: str) -> str:
    """The product name inside a family name (icd-redis -> redis), else ""."""
    for prefix in _FAMILY_PREFIXES:
        if name.startswith(prefix):
            return _phrase(name[len(prefix) :])
    for suffix in _FAMILY_SUFFIXES:
        if name.endswith(suffix):
            return _phrase(name[: -len(suffix)])
    return ""


def _service_from_index(entry: dict) -> _Service:
    """Build a _Service from an index entry, with priority from its category."""
    name = entry["name"]
    return _Service(
        key=name.replace("-", "_"),
        display=name,
        instance=name.replace("-", "_"),
        query=name,
        keywords=[_phrase(name)],
        name_match=[name],
        priority=_CATEGORY_PRIORITY.get(entry.get("category", ""), 5),
    )


def _claimed(picked: dict[str, _Service]) -> set[str]:
    """Phrases the keyword map has already answered for."""
    claimed: set[str] = set()
    for svc in picked.values():
        claimed.update(_phrase(k) for k in svc.keywords)
        claimed.update(_phrase(n) for n in svc.name_match)
        claimed.add(_phrase(svc.key))
    return claimed


def _index_matches(prompt: str, picked: dict[str, _Service]) -> list[_Service]:
    """Modules the index recognises in the prompt that the keyword map missed."""
    phrases, entries = _index_phrases()
    if not phrases:
        return []
    text = f" {_phrase(prompt)} "
    claimed = _claimed(picked)
    taken = {n for svc in picked.values() for n in svc.name_match}
    found: dict[str, _Service] = {}
    # Longest phrases first, so "event notifications" is preferred over a
    # single token that also appears in it.
    for phrase in sorted(phrases, key=lambda p: (-len(p.split()), p)):
        if phrase in claimed or f" {phrase} " not in text:
            continue
        name = phrases[phrase]
        if name in taken or name in found:
            continue
        found[name] = _service_from_index(entries[name])
    return list(found.values())


def _wants_workload(prompt: str) -> bool:
    """Whether the prompt seems to ask for a primary service/workload."""
    p = prompt.lower()
    return any(re.search(rf"\b{w}\b", p) for w in _WORKLOAD_INTENT)


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


_SVC_BY_KEY = {s.key: s for s in _SERVICES}


def _finalize(picked: dict[str, _Service]) -> list[_Service]:
    """Add the RG foundation + a VPC for clusters, then sort by deployment order."""
    if "resource_group" not in picked:
        picked["resource_group"] = _SVC_BY_KEY["resource_group"]
    if _NEEDS_VPC & set(picked) and "vpc" not in picked:
        picked["vpc"] = _SVC_BY_KEY["vpc"]
    return sorted(picked.values(), key=lambda s: (s.priority, s.key))


def _detect_services(prompt: str) -> list[_Service]:
    """Classify which services the prompt asks for (deduped, deployment-ordered)."""
    p = f" {prompt.lower()} "
    picked: dict[str, _Service] = {}
    matched_on: dict[str, str] = {}
    for svc in _SERVICES:
        if svc.key in picked:
            continue
        hit = next((kw for kw in svc.keywords if kw in p), None)
        if hit:
            picked[svc.key] = svc
            matched_on[svc.key] = _phrase(hit)
    # Anything the keyword map didn't recognise, the index might.
    text = f" {_phrase(prompt)} "
    for svc in _index_matches(prompt, picked):
        phrase = svc.keywords[0]
        # "watsonx orchestrate" is a better answer than the "watsonx" keyword
        # that also fired — unless that service was itself named outright.
        for key, keyword in list(matched_on.items()):
            named = f" {_phrase(picked[key].name_match[0])} " in text
            if not named and keyword != phrase and f" {keyword} " in f" {phrase} ":
                picked.pop(key, None)
                matched_on.pop(key, None)
        picked.setdefault(svc.key, svc)
    return _finalize(picked)


def _match_known(term: str) -> _Service | None:
    """Map a caller-supplied service term to a known _Service, or None."""
    t = f" {term.lower().strip()} "
    slug_key = re.sub(r"[^a-z0-9]+", "_", term.lower().strip()).strip("_")
    for svc in _SERVICES:
        if svc.key == slug_key or svc.instance == slug_key:
            return svc
        if any(kw in t for kw in svc.keywords):
            return svc
    # Fall back to the index before treating the term as an unknown workload.
    phrases, entries = _index_phrases()
    name = phrases.get(_phrase(term))
    return _service_from_index(entries[name]) if name else None


def _adhoc_service(term: str) -> _Service:
    """Build a generic workload _Service for a term not in the known map."""
    slug = re.sub(r"[^a-z0-9]+", "-", term.lower().strip()).strip("-") or "service"
    inst = slug.replace("-", "_")
    return _Service(
        key=inst,
        display=term.strip(),
        instance=inst,
        query=term.strip(),
        keywords=[term.lower()],
        name_match=[slug],
        priority=5,
    )


def _services_from_terms(terms: list[str]) -> list[_Service]:
    """Resolve caller-supplied service terms into _Service entries (ordered)."""
    picked: dict[str, _Service] = {}
    for term in terms:
        if not term or not term.strip():
            continue
        svc = _match_known(term) or _adhoc_service(term)
        picked.setdefault(svc.key, svc)
    return _finalize(picked)


def _is_connectable(input_name: str) -> bool:
    """Only wire inputs that look like a cross-module resource reference."""
    if input_name in _PREREQ_INPUTS:
        return False
    return bool(
        re.search(r"_(id|ids|crn|crns|guid|name)$", input_name)
    ) or input_name in {"vpc_subnets"}


# --- Kind vocabulary ------------------------------------------------------
#
# A module's "kind" is its service instance name (cos, kms, vpc, ...). Inputs
# name the kind of the thing they want (existing_cos_id wants a cos), so an
# input can be matched to a module without the names having to be identical.
# Matching is always scoped to the modules in *this* composition, so an input
# can never drift onto an unrelated module's similarly-typed output.

# Extra spellings a kind may appear under inside an input name.
_KIND_ALIASES: dict[str, set[str]] = {
    # "group" is what resource_group_id reduces to once the filler token
    # "resource" is dropped.
    "resource_group": {"group"},
    "cos": {"object_storage", "cos_bucket"},
    "kms": {"key_protect", "key_management", "hpcs", "kp"},
    "vpc": {"network"},
    "openshift": {"ocp", "cluster"},
    "iks": {"kubernetes", "cluster"},
    "secrets_manager": {"sm"},
    "event_streams": {"kafka"},
    "cloud_logs": {"logs"},
    "cloud_monitoring": {"monitoring"},
    "postgresql": {"postgres"},
    "mongodb": {"mongo"},
}

# Prefixes that mark a "bring your own" input rather than part of the kind.
_NOISE_PREFIXES = ("use_existing_", "existing_", "provided_", "source_")
# The value-type token an input asks for. Required: a name with no type token
# is never wired.
_TYPE_TOKENS = {
    "id",
    "ids",
    "crn",
    "crns",
    "guid",
    "guids",
    "name",
    "names",
    "endpoint",
}
# Tokens that carry no identity and are dropped before matching the kind.
_FILLER_TOKENS = {"instance", "resource", "service", "cloud"}

# Inputs whose names don't carry their own kind, mapped to the kind that
# produces them plus the output names to prefer, most specific first. This is
# the deliberate escape hatch for conventions like kms_key_crn; every entry is
# still subject to the "exactly one source module, exactly one output" guards.
_INPUT_ALIASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (r"kms.*key.*crn|encryption_key_crn|^key_crn$", "kms", (r"key.*crn", r"crn")),
    (r"kms.*key.*id$", "kms", (r"key.*id", r"_id$")),
    # Cluster modules take vpc_subnets as map(list(object({id, zone,
    # cidr_block}))), which is the shape of the VPC's subnet_detail_map —
    # the wiring shipped DAs use.
    (r"^vpc_subnets$", "vpc", (r"^subnet_detail_map$", r"^subnets$")),
    (r"^subnet_ids$", "vpc", (r"^subnet_ids$",)),
    (r"bucket.*(name|crn)$", "cos", (r"bucket.*(name|crn)$",)),
)


def _aliases_for(entry: dict) -> set[str]:
    """Every kind spelling that identifies this module."""
    instance = entry["instance"]
    return {instance} | _KIND_ALIASES.get(instance, set())


def _split_input(input_name: str) -> tuple[str, str] | None:
    """
    Split an input name into (kind, type), or None when it names no kind.

    ``existing_cos_id`` -> ("cos", "id"); ``kms_key_crn`` -> ("kms_key", "crn")
    (no module is a "kms_key", so that one falls through to the alias table).
    """
    name = input_name.lower()
    for prefix in _NOISE_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix) :]
            break
    parts = name.split("_")
    if len(parts) < 2 or parts[-1] not in _TYPE_TOKENS:
        return None
    kind_parts = [p for p in parts[:-1] if p and p not in _FILLER_TOKENS]
    if not kind_parts:
        return None
    return "_".join(kind_parts), parts[-1]


def _pick_output(
    instance: str, outputs: set[str], kind: str, type_token: str
) -> tuple[str | None, str]:
    """
    Choose the one output of ``instance`` that satisfies (kind, type).

    Returns (output, "") on a unique match, else (None, reason). Ambiguity is
    never resolved by guessing — an unwired input with a stated reason is
    better than a confidently wrong wire.
    """
    candidates = sorted(
        o for o in outputs if o == type_token or o.endswith(f"_{type_token}")
    )
    if not candidates:
        return None, f"{instance} exposes no '{type_token}' output"
    kind_tokens = set(kind.split("_"))
    ranks = (
        [
            o
            for o in candidates
            if o in {f"{kind}_{type_token}", f"{kind}_instance_{type_token}"}
        ],
        [o for o in candidates if kind_tokens <= set(o.split("_"))],
        # ICD-style modules expose a bare `id`/`crn` as their primary output.
        [o for o in candidates if o == type_token],
        candidates,
    )
    for rank in ranks:
        if len(rank) == 1:
            return rank[0], ""
        if len(rank) > 1:
            return None, (
                f"{instance} exposes several '{type_token}' outputs "
                f"({', '.join(rank)}) — confirm the right one with get_module_details"
            )
    return None, f"{instance} exposes no '{type_token}' output"


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
) -> tuple[dict[str, dict], set[str], list[str]]:
    """
    Return (inputs, output_names, provisions) for a module via the registry.

    Inputs are keyed by name and carry the registry's ``type``/``required``
    metadata: the matcher needs the type to spot nested (object) inputs it
    cannot wire, and ``required`` to rank the gaps it reports.

    ``provisions`` are the whole modules this one instantiates itself, read
    from the same payload — no extra call.
    """
    namespace, name, provider = parse_module_id(module_id)
    async with TerraformClient(
        config, cache=get_cache(), rate_limiter=get_rate_limiter()
    ) as tc:
        data = await tc.get_module_details(namespace, name, provider, version)
    root = data.get("root", {})
    inputs = {
        i["name"]: {
            "type": i.get("type", "") or "",
            "required": bool(i.get("required", False)),
            "description": (i.get("description", "") or "").strip(),
        }
        for i in root.get("inputs", [])
        if i.get("name")
    }
    outputs = {o.get("name", "") for o in root.get("outputs", [])}
    return inputs, outputs, _provisioned_modules(root.get("dependencies", []))


def _provisioned_modules(dependencies: list[dict]) -> list[str]:
    """
    The whole modules a module instantiates internally, from its dependencies.

    The registry lists every ``module`` block, most of which are plumbing —
    crn-parser, cbr-rule-module, icd-versions. Those are submodules of a
    utility repo (``//modules/...``) and say nothing about the architecture.
    A dependency on a whole module does: base-ocp-vpc instantiating
    terraform-ibm-modules/cos/ibm means the cluster can create its own COS.
    """
    provisions: list[str] = []
    for dependency in dependencies:
        source = (dependency.get("source") or "").strip()
        if not source or "//" in source or source in provisions:
            continue
        if len(source.split("/")) != 3:  # namespace/name/provider
            continue
        provisions.append(source)
    return sorted(provisions)


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


def _conn(source, output, target, input_name, origin) -> ModuleConnection:
    return ModuleConnection(
        source_module=source["instance"],
        source_output=output,
        target_module=target["instance"],
        target_input=input_name,
        origin=origin,
    )


def _match_input(
    input_name: str, target: dict, earlier: list[dict], later: list[dict]
) -> tuple[ModuleConnection | None, str, bool]:
    """
    Resolve one input against the modules deployed before it.

    Returns (connection, reason, source_found). On a miss the reason explains
    the gap, and source_found says whether a plausible source module was in the
    composition at all (i.e. whether this is a refusal or simply absent).
    """
    # Which module *owns* this input's value: the one whose kind the input
    # names (existing_cos_id -> cos), or the kind the alias table points at
    # (kms_key_crn -> kms). Identity beats name coincidence — modules re-export
    # values they consumed (cos also outputs kms_key_crn), and wiring from the
    # re-exporter would invent a dependency on the wrong module.
    kind, type_token, preferences = "", "", ()
    matches: list[dict] = []
    split = _split_input(input_name)
    if split:
        kind, type_token = split
        matches = [s for s in earlier if kind in _aliases_for(s)]
    wanted_kind = ""
    if not matches:
        for pattern, alias_kind, alias_preferences in _INPUT_ALIASES:
            if not re.search(pattern, input_name):
                continue
            alias_matches = [s for s in earlier if alias_kind in _aliases_for(s)]
            if alias_matches:
                kind, preferences, matches = (
                    alias_kind,
                    alias_preferences,
                    alias_matches,
                )
                break
            wanted_kind = wanted_kind or alias_kind

    if len(matches) > 1:
        names = ", ".join(m["instance"] for m in matches)
        return None, f"'{kind}' matches more than one module ({names})", True

    if matches:
        source = matches[0]
        # Exact output name, from the owning module: the confident match.
        if input_name in source["outputs"]:
            return _conn(source, input_name, target, input_name, "inferred"), "", True
        if preferences:
            # Alias tier: the input doesn't carry its kind, so the output to
            # use is named by convention rather than derived from the name.
            for preference in preferences:
                hits = sorted(o for o in source["outputs"] if re.search(preference, o))
                if len(hits) == 1:
                    return (
                        _conn(source, hits[0], target, input_name, "inferred-alias"),
                        "",
                        True,
                    )
                if len(hits) > 1:
                    return (
                        None,
                        (
                            f"{source['instance']} exposes several matching outputs "
                            f"({', '.join(hits)}) — confirm the right one with "
                            "get_module_details"
                        ),
                        True,
                    )
            return None, f"{source['instance']} exposes no matching output", True
        # Kind tier: same kind, same value type, one unambiguous output.
        output, reason = _pick_output(
            source["instance"], source["outputs"], kind, type_token
        )
        if output:
            return _conn(source, output, target, input_name, "inferred-kind"), "", True
        return None, reason, True

    # No module owns this input's kind. An exact output-name match anywhere in
    # the composition is still a strong signal, so fall back to it — unless the
    # alias table already told us which kind this input wants and that kind is
    # missing, in which case a same-named output is a re-export, not the source.
    if not wanted_kind:
        for source in earlier:
            # A module that both consumes and exposes the same name is passing
            # the value through, not producing it (cos echoes the resource group
            # it was given). Wiring from it would depend on the wrong module.
            if input_name in source["outputs"] and input_name not in source["inputs"]:
                return (
                    _conn(source, input_name, target, input_name, "inferred"),
                    "",
                    True,
                )

    kind = wanted_kind or kind
    if not kind:
        return None, "no matching module in this composition", False
    # The counterpart may be in the composition but deployed later — a real
    # link that the current (priority-based) order can't express.
    downstream = [s["instance"] for s in later if kind in _aliases_for(s)]
    if downstream:
        return (
            None,
            f"{', '.join(downstream)} is deployed after {target['instance']} in this "
            "order — reorder the modules or wire this one manually",
            True,
        )
    return None, f"no '{kind}' module in this composition", False


def _worth_reporting(input_name: str, target: dict, source_found: bool) -> bool:
    """
    Whether an unwired input is a real gap worth a note.

    ``_is_connectable`` is deliberately generous, so it also catches inputs that
    were never cross-module references: a module naming its own resource
    (``cluster_name`` on the cluster, ``existing_cos_instance_id`` on cos) and
    plain naming inputs (``dns_binding_name``). Reporting those buries the
    genuine gaps.
    """
    if source_found:
        return True
    split = _split_input(input_name)
    if not split:
        return True
    kind, type_token = split
    if kind in _aliases_for(target):
        return False  # names or re-uses the resource this module owns
    byo = input_name.lower().startswith(_NOISE_PREFIXES)
    return type_token not in {"name", "names"} or byo


def _dependency_edges(modules: list[dict]) -> dict[str, set[str]]:
    """
    Which modules each module consumes a value from, ignoring deployment order.

    The matcher normally only looks at modules deployed earlier, which makes the
    result depend on the order it is trying to establish. Here every other
    module is a candidate, so the edges describe the composition itself.
    """
    edges: dict[str, set[str]] = {m["instance"]: set() for m in modules}
    for target in modules:
        others = [m for m in modules if m["instance"] != target["instance"]]
        for input_name in sorted(target["inputs"]):
            if not _is_connectable(input_name):
                continue
            connection, _, _ = _match_input(input_name, target, others, [])
            if connection is not None:
                edges[target["instance"]].add(connection.source_module)
    return edges


def _order_modules(modules: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Order modules so every module follows the ones it consumes values from.

    A topological sort of the inferred connection graph, with the static
    service priority breaking ties, so a composition whose dependencies say
    nothing keeps the order it had. Returns (ordered, notes).
    """
    edges = _dependency_edges(modules)
    by_instance = {m["instance"]: m for m in modules}
    rank = {m["instance"]: (m["svc"].priority, m["svc"].key) for m in modules}
    pending = {i: set(deps) for i, deps in edges.items()}

    ordered: list[str] = []
    notes: list[str] = []
    while pending:
        ready = [i for i, deps in pending.items() if not deps]
        if not ready:
            # A cycle: two modules each want a value from the other. No order
            # satisfies both, so fall back to priority and say which ones.
            stuck = sorted(pending, key=lambda i: rank[i])
            notes.append(
                f"Circular references between {', '.join(stuck)} — no deployment "
                "order satisfies them all, so these are ordered by service "
                "priority and at least one link is left unwired."
            )
            ordered.extend(stuck)
            break
        nxt = min(ready, key=lambda i: rank[i])
        ordered.append(nxt)
        del pending[nxt]
        for deps in pending.values():
            deps.discard(nxt)
    return [by_instance[i] for i in ordered], notes


def _infer_connections(
    modules: list[dict],
) -> tuple[list[ModuleConnection], list[dict]]:
    """
    Infer connections from module interfaces.

    modules is an ordered list (deployment order) of dicts with keys:
    instance, inputs (dict name -> metadata), outputs (set).

    Returns (connections, gaps) — gaps being every connectable input that was
    deliberately left unwired, so nothing goes missing silently.
    """
    connections: list[ModuleConnection] = []
    gaps: list[dict] = []
    for i, target in enumerate(modules):
        for input_name in sorted(target["inputs"]):
            if not _is_connectable(input_name):
                continue
            connection, reason, source_found = _match_input(
                input_name, target, modules[:i], modules[i + 1 :]
            )
            if connection is not None:
                connections.append(connection)
                continue
            if not _worth_reporting(input_name, target, source_found):
                continue
            gaps.append(
                {
                    "instance": target["instance"],
                    "input": input_name,
                    "required": bool(target["inputs"][input_name].get("required")),
                    "reason": reason,
                    "source_found": source_found,
                }
            )
    return connections, gaps


# How many gaps to spell out per module, and how many modules to report on,
# before falling back to a count. Real modules expose dozens of optional
# reference inputs; the notes are a signal, not a dump.
_GAPS_PER_MODULE = 5
_GAP_NAMES_ONLY = 8
_MODULES_WITH_GAPS = 8


def _gap_notes(gaps: list[dict]) -> list[str]:
    """One note per module summarising the inputs left unwired."""
    by_module: dict[str, list[dict]] = {}
    for gap in gaps:
        by_module.setdefault(gap["instance"], []).append(gap)

    notes: list[str] = []
    for instance, module_gaps in list(by_module.items())[:_MODULES_WITH_GAPS]:
        # Spell out what the reader can act on: required inputs, and the ones
        # where the counterpart module is present but we refused to guess.
        ranked = sorted(
            module_gaps,
            key=lambda g: (not g["required"], not g["source_found"], g["input"]),
        )
        shown, rest = ranked[:_GAPS_PER_MODULE], ranked[_GAPS_PER_MODULE:]
        detail = "; ".join(
            f"{g['input']}{' (required)' if g['required'] else ''} — {g['reason']}"
            for g in shown
        )
        # The rest are named without reasons, so nothing is silently dropped.
        tail = ""
        if rest:
            names = [g["input"] for g in rest[:_GAP_NAMES_ONLY]]
            more = len(rest) - len(names)
            tail = f" Also unwired: {', '.join(names)}"
            tail += f" (+{more} more)." if more > 0 else "."
        notes.append(f"{instance}: unwired inputs — {detail}.{tail}")
    return notes


# Nested field names that look like a reference to another module's resource.
_NESTED_FIELD = re.compile(
    r"\b[a-z0-9_]+(?:crn|kms)[a-z0-9_]*\b|\b[a-z0-9_]+_ids?\b", re.I
)
_MAX_NESTED_NOTES = 3


def _nested_notes(modules: list[dict]) -> list[str]:
    """
    Flag object/list(object) inputs that carry references inside them.

    ``worker_pools`` holds its own KMS config; that wiring lives inside a
    nested field and can't be expressed as a module-level connection, so we
    say so rather than pretend the input isn't there.
    """
    found: list[tuple[int, int, str]] = []
    for order, module in enumerate(modules):
        for name, meta in sorted(module["inputs"].items()):
            declared = (meta.get("type") or "").strip()
            if not declared.startswith(("object(", "list(object(")):
                continue
            fields = sorted({f.lower() for f in _NESTED_FIELD.findall(declared)})[:3]
            if not fields:
                continue
            # Encryption/CRN references are the ones worth the reader's
            # attention; plain nested ids (CBR rules and friends) rank below.
            rank = 0 if any(re.search(r"crn|kms", f) for f in fields) else 1
            found.append(
                (
                    rank,
                    order,
                    f"{module['instance']}.{name} is a nested {declared.split('(')[0]} "
                    f"input carrying references ({', '.join(fields)}) — nested wiring "
                    "can't be expressed as a module-level connection; read the schema "
                    "with get_module_details.",
                )
            )
    return [note for _, _, note in sorted(found)[:_MAX_NESTED_NOTES]]


def _existing_toggle(module: dict, aliases: set[str]) -> str | None:
    """
    The boolean input that switches a module to an existing instance.

    base-ocp-vpc creates its own COS unless ``use_existing_cos`` is true, so
    wiring ``existing_cos_id`` alone changes nothing. Found by shape rather
    than by name: a bool input mentioning "existing" and the other module's
    kind.
    """
    for name, meta in sorted(module["inputs"].items()):
        if (meta.get("type") or "").strip() != "bool":
            continue
        tokens = set(name.split("_"))
        if "existing" in tokens and tokens & aliases:
            return name
    return None


def _provision_notes(
    modules: list[dict], connections: list[ModuleConnection]
) -> list[str]:
    """
    Flag modules that would provision a service the composition already has.

    A cluster that creates its own COS alongside a COS module in the same
    composition is two instances, not one — and the wiring that avoids it
    usually needs a flag set as well as an input wired.
    """
    by_source = {m["module"].id: m for m in modules if m.get("module")}
    notes: list[str] = []
    for module in modules:
        for source in module.get("provisions", []):
            other = by_source.get(source)
            if other is None or other["instance"] == module["instance"]:
                continue
            # Prefer the "bring your own" wire: that's the one the toggle
            # governs, and naming any other link here would misdirect.
            candidates = sorted(
                (
                    c
                    for c in connections
                    if c.target_module == module["instance"]
                    and c.source_module == other["instance"]
                ),
                key=lambda c: ("existing" not in c.target_input, c.target_input),
            )
            wired = candidates[0] if candidates else None
            toggle = _existing_toggle(module, _aliases_for(other))
            note = (
                f"{module['instance']} instantiates {source} itself, and this "
                f"composition also deploys it as '{other['instance']}'"
            )
            if wired and toggle:
                note += (
                    f" — {wired.target_input} is wired from it, but {module['instance']} "
                    f"only uses that when {toggle} is true; set it or you get two."
                )
            elif wired:
                note += (
                    f" — {wired.target_input} is wired from it; confirm with "
                    "get_module_details that no further flag is needed to stop "
                    f"{module['instance']} creating its own."
                )
            elif toggle:
                note += f" — set {toggle} and wire it, or you get two instances."
            else:
                note += " — expect two instances unless it is told to reuse one."
            notes.append(note)
    return notes


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
    """Fallback when no interface could be read and nothing can be derived."""
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


# A per-module label, not something supplied once for the whole composition.
_NOT_COMPOSITION_WIDE = {"name", "ibmcloud_api_key"}
# How many "use existing" options to list before saying how many remain.
_MAX_REUSE_PREREQS = 6


def _summarise(text: str, fallback: str) -> str:
    """First sentence of a registry description, trimmed."""
    first = (text or "").strip().split("\n")[0].strip()
    if not first:
        return fallback
    sentence = first.split(". ")[0].rstrip(".")
    if len(sentence) >= 40:
        return sentence + "."
    if len(first) > 160:
        first = first[:157].rsplit(" ", 1)[0] + "..."
    return first


def _derive_prerequisites(
    modules: list[dict], gaps: list[dict]
) -> tuple[list[CompositionPrerequisite], list[str]]:
    """
    Build the prerequisite list from what the modules actually declare.

    Three kinds, in the order a consumer meets them:
      1. the API key, which is provider-level and never a module input
      2. values supplied once for the whole stack (region, prefix, tags) —
         only those the resolved modules really take
      3. inputs nothing in the composition can supply: the ones left unwired,
         and the "use existing" options that let you bring your own instance
         instead of creating one, which is how DAs present them.
    """
    prerequisites = [
        CompositionPrerequisite(
            name="ibmcloud_api_key",
            type="secret",
            required=True,
            description="IBM Cloud API key for the provider.",
        )
    ]

    # 2. Composition-wide values, required if any module requires them.
    shared: dict[str, dict] = {}
    for module in modules:
        for name, meta in module["inputs"].items():
            if name not in _PREREQ_INPUTS or name in _NOT_COMPOSITION_WIDE:
                continue
            entry = shared.setdefault(
                name,
                {"type": meta.get("type") or "string", "required": False, "takers": []},
            )
            entry["required"] = entry["required"] or bool(meta.get("required"))
            entry["takers"].append(module["instance"])
    for name in sorted(shared, key=lambda n: (not shared[n]["required"], n)):
        entry = shared[name]
        # Deliberately not the registry description: each module words these
        # in terms of itself ("tags for the Key Protect instance"), which
        # reads as wrong once the value is supplied to the whole stack.
        prerequisites.append(
            CompositionPrerequisite(
                name=name,
                type=entry["type"],
                required=entry["required"],
                description=f"Supplied once, to: {', '.join(entry['takers'])}.",
            )
        )

    # 3. What the wiring could not supply.
    reuse, notes = [], []
    for gap in gaps:
        module = next(m for m in modules if m["instance"] == gap["instance"])
        meta = module["inputs"][gap["input"]]
        name = f"{gap['instance']}.{gap['input']}"
        byo = gap["input"].lower().startswith(_NOISE_PREFIXES)
        if gap["required"]:
            prerequisites.append(
                CompositionPrerequisite(
                    name=name,
                    type=meta.get("type") or "string",
                    required=True,
                    description=_summarise(
                        meta.get("description", ""),
                        f"Required by {gap['instance']} and not produced by any "
                        "module here.",
                    ),
                )
            )
        elif byo:
            reuse.append(
                CompositionPrerequisite(
                    name=name,
                    type=meta.get("type") or "string",
                    required=False,
                    description=_summarise(
                        meta.get("description", ""),
                        "Supply an existing resource instead of creating one.",
                    ),
                )
            )

    reuse.sort(key=lambda p: p.name)
    prerequisites.extend(reuse[:_MAX_REUSE_PREREQS])
    if len(reuse) > _MAX_REUSE_PREREQS:
        remaining = len(reuse) - _MAX_REUSE_PREREQS
        notes.append(
            f"{remaining} further 'use existing' input"
            f"{'s' if remaining > 1 else ''} can also take an existing resource; "
            "the full set is in each module's get_module_details."
        )
    return prerequisites, notes


async def _resolve_service(svc: _Service, config: Config):
    """Search for one service's module; None when it can't be resolved."""
    try:
        return await _search_best(svc, config)
    except Exception as e:  # noqa: BLE001 - one service failing isn't fatal
        logger.warning("search_modules failed", service=svc.key, error=str(e))
        return None


async def _interface_for(
    entry: dict, config: Config
) -> tuple[dict[str, dict], set[str], list[str]] | None:
    """Read one module's interface; None when it can't be read."""
    module = entry["module"]
    try:
        return await _fetch_interface(module.id, module.version, config)
    except Exception as e:  # noqa: BLE001 - wiring degrades, the tool still answers
        logger.warning("get_module_details failed", module_id=module.id, error=str(e))
        return None


async def generate_module_composition_impl(
    request: GenerateModuleCompositionRequest, config: Config
) -> ModuleComposition:
    """Assemble a composition live from the registry for the request."""
    prompt_text = (request.prompt or "").strip()
    # Prefer the caller-supplied service list; fall back to parsing the prompt.
    if request.services:
        services = _services_from_terms(request.services)
    else:
        services = _detect_services(prompt_text)
    da = request.include_da or (bool(prompt_text) and _mentions_da(prompt_text))
    notes: list[str] = []

    # 1. Resolve each service to a real module + version via search_modules.
    #    The searches are independent, so they all go out at once.
    modules = await asyncio.gather(*(_resolve_service(s, config) for s in services))
    resolved: list[dict] = []
    for svc, module in zip(services, modules, strict=True):
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

    # 2. Fetch each module's interface (inputs/outputs) via get_module_details,
    #    again in parallel.
    interfaces = await asyncio.gather(*(_interface_for(e, config) for e in resolved))
    for entry, interface in zip(resolved, interfaces, strict=True):
        if interface is None:
            notes.append(
                f"Could not read the interface for {entry['module'].id}; "
                "wiring may be incomplete."
            )
            interface = ({}, set(), [])
        entry["inputs"], entry["outputs"], entry["provisions"] = interface

    # 3. Order the modules by what they actually consume from each other,
    #    rather than by static service priority alone.
    resolved, order_notes = _order_modules(resolved)
    notes.extend(order_notes)
    deployment_order = [e["instance"] for e in resolved]

    # 4. Connections: inferred from interfaces; reference the DA when requested.
    # Connections are always inferred from module interfaces (real DAs route
    # their wiring through locals/interpolation that can't be extracted reliably).
    connections, gaps = _infer_connections(resolved)

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

    # Report every connectable input left unwired, plus nested inputs whose
    # references can't be expressed as module-level connections.
    notes.extend(_gap_notes(gaps))
    notes.extend(_nested_notes(resolved))
    notes.extend(_provision_notes(resolved, connections))

    # Prerequisites come from what the modules actually declare; fall back to
    # the standard set when no interface could be read.
    prerequisites, prereq_notes = _derive_prerequisites(resolved, gaps)
    notes.extend(prereq_notes)
    if len(prerequisites) == 1:
        prerequisites = _standard_prerequisites()

    # For the prompt path, flag when we recognised no service or no primary
    # workload, so unmapped services aren't dropped silently. Skipped when the
    # caller passed an explicit `services` list (nothing was guessed).
    if not request.services:
        resolved_services = [e["svc"] for e in resolved]
        non_foundation = [s for s in resolved_services if s.key != "resource_group"]
        has_workload = any(s.priority >= 5 for s in resolved_services)
        if not non_foundation:
            notes.insert(
                0,
                "No IBM Cloud services were recognised in the request. Name the "
                "services you want (e.g. 'openshift with kms and cos'), or use "
                "search_modules to find modules and add them.",
            )
        elif not has_workload and _wants_workload(prompt_text):
            notes.insert(
                0,
                "No primary workload/service was recognised. If you named a service "
                "the tool doesn't map yet, find it with search_modules and add it "
                "manually.",
            )

    primary = next((e for e in resolved if e["svc"].priority == 5), resolved[-1])
    composition_name = f"{primary['svc'].key}-composition"
    effective_prompt = prompt_text or "services: " + ", ".join(request.services or [])

    logger.info(
        "Assembled composition",
        request=effective_prompt,
        modules=len(resolved),
        connections=len(connections),
        da_grounded=reference_solution is not None,
    )

    return ModuleComposition(
        composition_name=composition_name,
        description=_describe([e["svc"] for e in resolved]),
        prompt=effective_prompt,
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
                provisions=e.get("provisions", []),
            )
            for e in resolved
        ],
        deployment_order=deployment_order,
        connections=connections,
        prerequisites=prerequisites,
        notes=notes,
    )

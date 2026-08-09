"""
Module composition suggestion tool for TIM-MCP.

This module implements ``generate_module_composition``: given a service name,
architecture keyword, or composition name, it returns a curated, DA-derived
recommendation of the module stack (modules, deployment order, inter-module
wiring, and prerequisites) needed to build a common IBM Cloud architecture
pattern.

The compositions themselves are baked-in knowledge stored in
``static/compositions.json``. Module versions and registry sources are resolved
at request time from ``static/module_index.json`` so the recommendation always
pins the latest indexed version without duplicating that data.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import Config
from ..exceptions import TIMError
from ..logging import get_logger
from ..types import (
    CompositionPrerequisite,
    CompositionSummary,
    GenerateModuleCompositionRequest,
    GenerateModuleCompositionResponse,
    ModuleComposition,
    ModuleConnection,
    RecommendedModule,
    ReferenceSolution,
)

logger = get_logger(__name__)

VALID_ENVIRONMENTS = {"production", "development"}


def _find_static_file(filename: str) -> Path:
    """
    Locate a file in the static directory (packaged or development layout).

    Args:
        filename: Name of the file within the static directory.

    Returns:
        Path to the file.

    Raises:
        FileNotFoundError: If the file cannot be found in either location.
    """
    # Packaged location (tim_mcp/static/...) then development location (static/...)
    packaged_path = Path(__file__).parent.parent / "static" / filename
    dev_path = Path(__file__).parent.parent.parent / "static" / filename

    for file_path in (packaged_path, dev_path):
        if file_path.exists():
            return file_path

    raise FileNotFoundError(
        f"Required file '{filename}' not found. Searched:\n"
        f"  - {packaged_path}\n"
        f"  - {dev_path}"
    )


@lru_cache(maxsize=1)
def _load_compositions() -> list[dict[str, Any]]:
    """Load and cache the baked-in composition catalog."""
    path = _find_static_file("compositions.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    compositions = data.get("compositions", [])
    if not isinstance(compositions, list):
        raise TIMError("Invalid compositions.json: 'compositions' must be a list")
    return compositions


@lru_cache(maxsize=1)
def _load_module_lookup() -> dict[str, dict[str, str]]:
    """
    Build a lookup from base module ID to its latest version and source URL.

    Returns a mapping like::

        {"terraform-ibm-modules/vpc/ibm": {"version": "1.7.0", "source_url": "..."}}

    Missing or unreadable index files degrade gracefully to an empty lookup so
    the tool still returns compositions (without pinned versions).
    """
    lookup: dict[str, dict[str, str]] = {}
    try:
        path = _find_static_file("module_index.json")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(
            "Could not load module index for version resolution", error=str(e)
        )
        return lookup

    for module in data.get("modules", []):
        full_id = module.get("id", "")
        parts = full_id.split("/")
        if len(parts) < 4:
            continue
        base_id = "/".join(parts[:3])
        version = parts[3]
        lookup[base_id] = {
            "version": version,
            "source_url": module.get("source_url", ""),
        }
    return lookup


def _enrich_modules(raw_modules: list[dict[str, Any]]) -> list[RecommendedModule]:
    """Attach resolved version and registry metadata to each recommended module."""
    lookup = _load_module_lookup()
    enriched: list[RecommendedModule] = []
    for module in raw_modules:
        base_id = module["id"]
        meta = lookup.get(base_id, {})
        version = meta.get("version")
        registry_url = (
            f"https://registry.terraform.io/modules/{base_id}/{version}"
            if version
            else None
        )
        enriched.append(
            RecommendedModule(
                id=base_id,
                instance_name=module["instance_name"],
                role=module.get("role", "core"),
                purpose=module["purpose"],
                version=version,
                source=base_id,
                registry_url=registry_url,
            )
        )
    return enriched


def _build_reference_solution(raw: dict[str, Any] | None) -> ReferenceSolution | None:
    """Build the anchor DA pointer, adding a get_content fetch hint with the version."""
    if not raw:
        return None
    module_id = raw["module_id"]
    version = _load_module_lookup().get(module_id, {}).get("version")
    module_ref = f"{module_id}/{version}" if version else module_id
    fetch_hint = (
        f'get_content(module_id="{module_ref}", '
        f'path="{raw["solution_path"]}", include_files=["*.tf"])'
    )
    return ReferenceSolution(
        module_id=module_id,
        solution_path=raw["solution_path"],
        source_url=raw["source_url"],
        fetch_hint=fetch_hint,
    )


def _build_composition(raw: dict[str, Any]) -> ModuleComposition:
    """Convert a raw composition dict into a validated ModuleComposition."""
    return ModuleComposition(
        composition_name=raw["name"],
        display_name=raw["display_name"],
        description=raw["description"],
        category=raw["category"],
        environment=raw["environment"],
        reference_solution=_build_reference_solution(raw.get("reference_solution")),
        recommended_modules=_enrich_modules(raw["recommended_modules"]),
        deployment_order=raw["deployment_order"],
        connections=[ModuleConnection(**c) for c in raw["connections"]],
        prerequisites=[CompositionPrerequisite(**p) for p in raw["prerequisites"]],
        notes=raw.get("notes", []),
    )


def _summary(raw: dict[str, Any]) -> CompositionSummary:
    """Build a lightweight summary of a composition."""
    return CompositionSummary(
        composition_name=raw["name"],
        display_name=raw["display_name"],
        category=raw["category"],
        environment=raw["environment"],
        services=raw.get("services", []),
    )


def _match_terms(raw: dict[str, Any]) -> set[str]:
    """Collect the lowercased terms a composition can be matched against."""
    terms: set[str] = set()
    terms.add(raw["name"].lower())
    terms.add(raw["display_name"].lower())
    terms.add(raw["category"].lower())
    terms.update(s.lower() for s in raw.get("services", []))
    terms.update(k.lower() for k in raw.get("keywords", []))
    return terms


def _score(raw: dict[str, Any], query: str, tokens: list[str]) -> int:
    """
    Score how well a composition matches the query. Higher is better; 0 = no match.
    """
    terms = _match_terms(raw)
    score = 0

    # Whole-query substring match against any term (strong signal).
    for term in terms:
        if query == term:
            score += 10
        elif query in term or term in query:
            score += 4

    # Per-token matches (handles multi-word queries like "event streams").
    for token in tokens:
        if token in terms:
            score += 3
        else:
            for term in terms:
                if token in term:
                    score += 1
                    break
    return score


async def generate_module_composition_impl(
    request: GenerateModuleCompositionRequest, config: Config
) -> GenerateModuleCompositionResponse:
    """
    Implementation for the ``generate_module_composition`` MCP tool.

    Args:
        request: Validated request with the service/pattern and optional environment.
        config: Server configuration (unused today; kept for signature consistency).

    Returns:
        A GenerateModuleCompositionResponse with the best-matching composition,
        any alternatives, and (when nothing matches) the full catalog.
    """
    compositions = _load_compositions()

    query = request.service_or_pattern.strip().lower()
    tokens = [t for t in query.replace("-", " ").replace("_", " ").split() if t]

    environment = request.environment.strip().lower() if request.environment else None
    if environment and environment not in VALID_ENVIRONMENTS:
        # Treat an unknown environment as "no preference" rather than failing.
        logger.warning("Unknown environment, ignoring", environment=environment)
        environment = None

    # 1. Exact composition-name match short-circuits everything.
    for raw in compositions:
        if raw["name"].lower() == query:
            return GenerateModuleCompositionResponse(
                matched=True,
                query=request.service_or_pattern,
                composition=_build_composition(raw),
                message=f"Exact match for composition '{raw['name']}'.",
            )

    # 2. Score every composition and keep the positive matches.
    scored = [(raw, _score(raw, query, tokens)) for raw in compositions]
    matches = [(raw, s) for raw, s in scored if s > 0]

    # 3. Bias by environment when one was requested and it helps disambiguate.
    if environment and matches:
        env_matches = [
            (raw, s) for raw, s in matches if raw["environment"] == environment
        ]
        if env_matches:
            matches = env_matches

    if not matches:
        logger.info("No composition matched", query=query)
        return GenerateModuleCompositionResponse(
            matched=False,
            query=request.service_or_pattern,
            available_compositions=[_summary(raw) for raw in compositions],
            message=(
                f"No baked-in composition matched '{request.service_or_pattern}'. "
                "Pick one of the available_compositions by name, or search for "
                "individual modules with search_modules and compose them manually."
            ),
        )

    # Sort by score (desc), then by name for deterministic ordering.
    matches.sort(key=lambda item: (-item[1], item[0]["name"]))
    best_raw = matches[0][0]
    alternatives = [_summary(raw) for raw, _ in matches[1:]]

    logger.info(
        "Composition matched",
        query=query,
        composition=best_raw["name"],
        alternatives=len(alternatives),
    )

    return GenerateModuleCompositionResponse(
        matched=True,
        query=request.service_or_pattern,
        composition=_build_composition(best_raw),
        alternatives=alternatives,
        message=(
            f"Best match: '{best_raw['name']}'."
            + (
                f" {len(alternatives)} alternative(s) also matched."
                if alternatives
                else ""
            )
        ),
    )

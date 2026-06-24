from __future__ import annotations

SimpleSourceStatusSpec = tuple[set[str], set[str], str, str, str]

SIMPLE_SOURCE_STATUS_SPECS: dict[str, SimpleSourceStatusSpec] = {
    "bootstrap_preflight": ({"pass"}, set(), "bootstrap_preflight_failed", "", ""),
    "source_package_clean_extract": (
        {"pass"},
        set(),
        "source_package_clean_extract_failed",
        "",
        "",
    ),
    "raw_registry": (
        {"pass"},
        {"warn"},
        "raw_registry_preflight_failed",
        "raw_registry_preflight_warnings",
        "raw registry preflight emitted warnings; this is accepted as release advisory risk.",
    ),
    "generated_index": (
        {"pass"},
        {"attention"},
        "generated_index_unknown_status",
        "generated_index_archive_advisory",
        "generated artifact index reports archive candidates as advisory release risk.",
    ),
    "supply_chain_gate": ({"pass"}, set(), "supply_chain_gate_failed", "", ""),
    "sbom_readiness": ({"pass"}, set(), "sbom_readiness_gate_failed", "", ""),
}


def simple_source_status_spec(name: str) -> SimpleSourceStatusSpec | None:
    return SIMPLE_SOURCE_STATUS_SPECS.get(name)

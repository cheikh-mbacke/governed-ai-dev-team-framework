"""Design Authority & Visual Conformance Pipeline.

Turns human-provided mockups into governed, versioned, verifiable design
contracts that bind to Work Units, flow into multimodal Context Packages,
and are checked by an independent Visual Conformance Runner.

Import submodules directly when used from CommandGateway handlers to avoid
pulling the Execution Gateway during command package import.
"""

from __future__ import annotations

from governed_ai.core.design_authority.binding import (
    DesignBindingError,
    bind_design_to_work_unit,
    default_design_mode_for_work_unit,
    evaluate_g1_design_readiness,
)
from governed_ai.core.design_authority.conformance import (
    ConformanceError,
    run_visual_conformance,
)
from governed_ai.core.design_authority.contract import (
    DesignContractError,
    compile_design_contract,
    load_design_contract,
)
from governed_ai.core.design_authority.context import build_multimodal_design_context
from governed_ai.core.design_authority.design_system import (
    detect_design_system_conflict,
    find_existing_component,
    load_inventory,
    require_search_before_create,
    save_inventory,
)
from governed_ai.core.design_authority.models import (
    AUTHORITY_LEVELS,
    DESIGN_MODES,
    MODE_TO_PROCEDURE,
    SCHEMA_VERSION,
)
from governed_ai.core.design_authority.procedure_select import (
    ProcedureSelectionError,
    assert_procedure_matches_binding,
    select_frontend_procedure,
)
from governed_ai.core.design_authority.reconcile import reconcile_design_revision
from governed_ai.core.design_authority.reference_set import (
    ReferenceSetError,
    create_reference_set,
    load_reference_set,
    revalidate_reference_set,
)
from governed_ai.core.design_authority.registry import (
    DesignRegistryError,
    list_artifacts,
    load_artifact,
    register_local_artifact,
    register_remote_artifact,
    set_authority_level,
    verify_artifact_integrity,
)

__all__ = [
    "AUTHORITY_LEVELS",
    "DESIGN_MODES",
    "MODE_TO_PROCEDURE",
    "SCHEMA_VERSION",
    "ConformanceError",
    "DesignBindingError",
    "DesignContractError",
    "DesignRegistryError",
    "ProcedureSelectionError",
    "ReferenceSetError",
    "assert_procedure_matches_binding",
    "bind_design_to_work_unit",
    "build_multimodal_design_context",
    "compile_design_contract",
    "create_reference_set",
    "default_design_mode_for_work_unit",
    "detect_design_system_conflict",
    "evaluate_g1_design_readiness",
    "find_existing_component",
    "list_artifacts",
    "load_artifact",
    "load_design_contract",
    "load_inventory",
    "load_reference_set",
    "reconcile_design_revision",
    "register_local_artifact",
    "register_remote_artifact",
    "require_search_before_create",
    "revalidate_reference_set",
    "run_visual_conformance",
    "save_inventory",
    "select_frontend_procedure",
    "set_authority_level",
    "verify_artifact_integrity",
]


def __getattr__(name: str):
    if name in {"assert_visual_capabilities", "merge_visual_capabilities"}:
        from governed_ai.core.design_authority import visual_capabilities as _vc

        return getattr(_vc, name)
    raise AttributeError(name)

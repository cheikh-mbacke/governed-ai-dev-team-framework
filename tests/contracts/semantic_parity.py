"""Semantic parity between Published Contract Bundle v1 and Cursor adapter artefacts.

Document 13 §5 Phase 2 compatibility — detect drift before compiler cutover.
Lives under tests/ so Core/contracts stay free of adapter path literals.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "to",
        "for",
        "of",
        "in",
        "on",
        "with",
        "when",
        "without",
        "using",
        "from",
        "its",
        "their",
        "that",
        "this",
        "be",
        "is",
        "are",
        "as",
        "at",
        "by",
        "it",
        "not",
        "do",
        "does",
        "required",
        "explicit",
        "human",
    }
)

ADAPTER_ONLY_AGENTS = frozenset({"auth-smoke"})
PROCEDURE_SKILL_ALIASES = {"retrospective": "capture-feedback"}
ROLE_AGENT_ALIASES: dict[str, str] = {}
CONTROL_PLANE_ROLE_ID = "control-plane"
IMPLEMENT_WORK_UNIT_PROCEDURE = "implement-work-unit"
SECURITY_REVIEW_PROCEDURE = "security-review"


@dataclass(frozen=True)
class ParityDivergence:
    kind: str
    identifier: str
    field: str
    message: str
    bundle_value: str | None = None
    cursor_value: str | None = None
    cursor_path: str | None = None

    def format(self) -> str:
        parts = [f"[{self.kind}:{self.identifier}] {self.field}: {self.message}"]
        if self.cursor_path:
            parts.append(f"  cursor: {self.cursor_path}")
        if self.bundle_value is not None:
            parts.append(f"  bundle: {self.bundle_value!r}")
        if self.cursor_value is not None:
            parts.append(f"  cursor_value: {self.cursor_value!r}")
        return "\n".join(parts)


def _normalize_text(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _significant_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


def _text_overlap_ratio(left: str, right: str) -> float:
    left_tokens = _significant_tokens(left)
    right_tokens = _significant_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def _texts_align(expected: str, observed: str, *, min_overlap: float = 0.45) -> bool:
    expected_norm = _normalize_text(expected)
    observed_norm = _normalize_text(observed)
    if expected_norm in observed_norm or observed_norm in expected_norm:
        return True
    return _text_overlap_ratio(expected, observed) >= min_overlap


def _invariant_reflected(invariant: str, combined: str) -> bool:
    if _texts_align(invariant, combined, min_overlap=0.25):
        return True
    inv_tokens = _significant_tokens(invariant)
    if not inv_tokens:
        return True
    overlap = inv_tokens & _significant_tokens(combined)
    return len(overlap) >= min(2, len(inv_tokens))


def _parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw
    meta = yaml.safe_load(match.group(1)) or {}
    body = match.group(2)
    if not isinstance(meta, dict):
        meta = {}
    return {str(k): str(v) if v is not None else "" for k, v in meta.items()}, body


def _expected_readonly(product_level: str) -> bool:
    return product_level == "none"


def _load_bundle_roles(bundle_dir: Path) -> dict[str, dict]:
    roles: dict[str, dict] = {}
    for path in sorted((bundle_dir / "roles").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        roles[doc["role_id"]] = doc
    return roles


def _load_bundle_procedures(bundle_dir: Path) -> dict[str, dict]:
    procedures: dict[str, dict] = {}
    for path in sorted((bundle_dir / "procedures").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        procedures[doc["procedure_id"]] = doc
    return procedures


def _load_compiler_notes() -> dict[str, list[str]]:
    sidecar = Path(__file__).resolve().parents[2] / "adapters" / "cursor" / "compiler-notes.yaml"
    if not sidecar.is_file():
        return {}
    data = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
    procedures = data.get("procedures") or {}
    mapping: dict[str, list[str]] = {}
    for procedure_id, entry in procedures.items():
        sources = entry.get("adapter_sources") if isinstance(entry, dict) else None
        if sources:
            mapping[str(procedure_id)] = [str(s) for s in sources]
    return mapping


def _default_procedure_sources(procedure_id: str) -> list[str]:
    if procedure_id == IMPLEMENT_WORK_UNIT_PROCEDURE:
        return ["agents/backend-developer.md", "agents/frontend-developer.md"]
    if procedure_id == SECURITY_REVIEW_PROCEDURE:
        return ["agents/security-reviewer.md"]
    skill_name = PROCEDURE_SKILL_ALIASES.get(procedure_id, procedure_id)
    return [f"skills/{skill_name}/SKILL.md"]


def _resolve_role_cursor_paths(role_id: str, repo_root: Path) -> list[Path]:
    if role_id == CONTROL_PLANE_ROLE_ID:
        return [repo_root / ".cursor" / "skills" / "orchestrator" / "SKILL.md"]
    agent_name = ROLE_AGENT_ALIASES.get(role_id, role_id)
    return [repo_root / ".cursor" / "agents" / f"{agent_name}.md"]


def _resolve_procedure_cursor_paths(
    procedure_id: str,
    repo_root: Path,
    compiler_notes: dict[str, list[str]],
) -> list[Path]:
    rel_paths = compiler_notes.get(procedure_id) or _default_procedure_sources(procedure_id)
    return [repo_root / ".cursor" / rel_path for rel_path in rel_paths]


def _check_role_parity(
    role_id: str,
    role: dict,
    cursor_paths: list[Path],
) -> list[ParityDivergence]:
    divergences: list[ParityDivergence] = []
    for path in cursor_paths:
        if not path.is_file():
            divergences.append(
                ParityDivergence(
                    kind="role",
                    identifier=role_id,
                    field="coverage",
                    message="expected Cursor artefact missing",
                    cursor_path=str(path),
                )
            )
            continue

        meta, body = _parse_frontmatter(path)
        rel = path.as_posix()

        expected_name = role_id if role_id != CONTROL_PLANE_ROLE_ID else "orchestrator"
        actual_name = meta.get("name", "")
        if actual_name != expected_name:
            divergences.append(
                ParityDivergence(
                    kind="role",
                    identifier=role_id,
                    field="name",
                    message="frontmatter name mismatch",
                    bundle_value=expected_name,
                    cursor_value=actual_name,
                    cursor_path=rel,
                )
            )

        mandate = role.get("mandate", "")
        description = meta.get("description", "")
        combined = f"{description}\n{body}"
        if not _texts_align(mandate, combined):
            divergences.append(
                ParityDivergence(
                    kind="role",
                    identifier=role_id,
                    field="mandate",
                    message="mandate not reflected in Cursor description/body",
                    bundle_value=mandate,
                    cursor_value=description,
                    cursor_path=rel,
                )
            )

        if role_id != CONTROL_PLANE_ROLE_ID:
            product_level = role["writes"]["product"]["level"]
            expected_ro = _expected_readonly(product_level)
            readonly_raw = meta.get("readonly", "")
            if readonly_raw == "":
                divergences.append(
                    ParityDivergence(
                        kind="role",
                        identifier=role_id,
                        field="readonly",
                        message="readonly frontmatter missing",
                        bundle_value=str(expected_ro),
                        cursor_path=rel,
                    )
                )
            else:
                actual_ro = readonly_raw.lower() == "true"
                if actual_ro != expected_ro:
                    divergences.append(
                        ParityDivergence(
                            kind="role",
                            identifier=role_id,
                            field="readonly",
                            message="readonly does not match writes.product.level",
                            bundle_value=f"{product_level} -> {expected_ro}",
                            cursor_value=str(actual_ro),
                            cursor_path=rel,
                        )
                    )

            model_pref = role.get("model_preference", "inherit")
            model = meta.get("model", "")
            if model and model != model_pref:
                divergences.append(
                    ParityDivergence(
                        kind="role",
                        identifier=role_id,
                        field="model",
                        message="model preference mismatch",
                        bundle_value=model_pref,
                        cursor_value=model,
                        cursor_path=rel,
                    )
                )

    return divergences


def _check_procedure_parity(
    procedure_id: str,
    procedure: dict,
    cursor_paths: list[Path],
) -> list[ParityDivergence]:
    divergences: list[ParityDivergence] = []
    intent = procedure.get("intent", "")
    invariants = procedure.get("invariants") or []
    steps = procedure.get("steps") or []

    existing = [p for p in cursor_paths if p.is_file()]
    if not existing:
        for path in cursor_paths:
            divergences.append(
                ParityDivergence(
                    kind="procedure",
                    identifier=procedure_id,
                    field="coverage",
                    message="expected Cursor artefact missing",
                    cursor_path=str(path),
                )
            )
        return divergences

    combined_parts: list[str] = []
    for path in existing:
        meta, body = _parse_frontmatter(path)
        combined_parts.append(meta.get("description", ""))
        combined_parts.append(body)
    combined = "\n".join(combined_parts)

    if not _texts_align(intent, combined):
        divergences.append(
            ParityDivergence(
                kind="procedure",
                identifier=procedure_id,
                field="intent",
                message="intent not reflected in Cursor skill/agent body",
                bundle_value=intent,
                cursor_value=combined[:200],
                cursor_path=", ".join(p.as_posix() for p in existing),
            )
        )

    for idx, invariant in enumerate(invariants):
        if not _invariant_reflected(invariant, combined):
            divergences.append(
                ParityDivergence(
                    kind="procedure",
                    identifier=procedure_id,
                    field=f"invariants[{idx}]",
                    message="invariant not reflected in Cursor body",
                    bundle_value=invariant,
                    cursor_path=", ".join(p.as_posix() for p in existing),
                )
            )

    missing_steps = [
        step
        for step in steps
        if not _texts_align(step, combined, min_overlap=0.3)
    ]
    if steps and len(missing_steps) > len(steps) // 2:
        divergences.append(
            ParityDivergence(
                kind="procedure",
                identifier=procedure_id,
                field="steps",
                message=(
                    f"{len(missing_steps)}/{len(steps)} agnostic steps lack semantic "
                    "reflection in Cursor body"
                ),
                bundle_value=missing_steps[0][:120],
                cursor_path=", ".join(p.as_posix() for p in existing),
            )
        )

    return divergences


def _check_extra_cursor_artefacts(
    repo_root: Path,
    roles: dict[str, dict],
    procedures: dict[str, dict],
) -> list[ParityDivergence]:
    divergences: list[ParityDivergence] = []
    expected_agents = {rid for rid in roles if rid != CONTROL_PLANE_ROLE_ID}
    expected_agents |= {SECURITY_REVIEW_PROCEDURE.replace("-review", "-reviewer")}

    for agent_path in sorted((repo_root / ".cursor" / "agents").glob("*.md")):
        agent_id = agent_path.stem
        if agent_id in ADAPTER_ONLY_AGENTS:
            continue
        if agent_id not in expected_agents:
            divergences.append(
                ParityDivergence(
                    kind="coverage",
                    identifier=agent_id,
                    field="extra_agent",
                    message="Cursor agent without bundle role mapping",
                    cursor_path=agent_path.as_posix(),
                )
            )

    mapped_skills = set(PROCEDURE_SKILL_ALIASES.values()) | {"orchestrator"}
    for procedure_id in procedures:
        if procedure_id in {IMPLEMENT_WORK_UNIT_PROCEDURE, SECURITY_REVIEW_PROCEDURE}:
            continue
        mapped_skills.add(PROCEDURE_SKILL_ALIASES.get(procedure_id, procedure_id))

    for skill_dir in sorted((repo_root / ".cursor" / "skills").iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name not in mapped_skills:
            divergences.append(
                ParityDivergence(
                    kind="coverage",
                    identifier=skill_dir.name,
                    field="extra_skill",
                    message="Cursor skill without bundle procedure mapping",
                    cursor_path=skill_dir.as_posix(),
                )
            )

    return divergences


def check_semantic_parity(
    repo_root: Path,
    bundle_dir: Path | None = None,
) -> list[ParityDivergence]:
    """Compare bundle v1 roles/procedures to live Cursor agents/skills."""
    bundle_dir = bundle_dir or (
        repo_root / "src" / "governed_ai" / "contracts" / "bundles" / "v1"
    )
    roles = _load_bundle_roles(bundle_dir)
    procedures = _load_bundle_procedures(bundle_dir)
    compiler_notes = _load_compiler_notes()

    divergences: list[ParityDivergence] = []
    for role_id, role in sorted(roles.items()):
        paths = _resolve_role_cursor_paths(role_id, repo_root)
        divergences.extend(_check_role_parity(role_id, role, paths))

    for procedure_id, procedure in sorted(procedures.items()):
        paths = _resolve_procedure_cursor_paths(procedure_id, repo_root, compiler_notes)
        divergences.extend(_check_procedure_parity(procedure_id, procedure, paths))

    divergences.extend(_check_extra_cursor_artefacts(repo_root, roles, procedures))
    return divergences


def format_divergence_report(divergences: list[ParityDivergence]) -> str:
    if not divergences:
        return "No semantic parity divergences detected."
    lines = [f"Semantic parity divergences ({len(divergences)}):", ""]
    lines.extend(d.format() for d in divergences)
    return "\n".join(lines)

#!/usr/bin/env python3
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

try:
    import yaml
except ModuleNotFoundError:
    from install_paths import requirements_install_hint

    print("Missing dependency: PyYAML. Install it first, then re-run this command:")
    print(f"  {requirements_install_hint(_ROOT)}")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

from i18n import project_language, t
from install_paths import bootstrap_runtime

ROOT = _ROOT
LANG = project_language(ROOT)
bootstrap_runtime(ROOT)

from governed_ai.core.commands.errors import GatewayError, exit_code_for
from governed_ai.core.orchestrator.progress import evaluate_run_progress
from governed_ai.core.workspace import Workspace
from governed_ai.core.workspace_mode import ensure_client_cycle_allowed
from governed_ai.notifications.config import load_smtp_settings, public_smtp_status

WORKSPACE = Workspace.from_root(ROOT)
try:
    ensure_client_cycle_allowed(WORKSPACE)
except GatewayError as exc:
    print(exc.message, file=sys.stderr)
    raise SystemExit(exit_code_for(exc.code)) from None
AI = WORKSPACE.ai_team
state = yaml.safe_load((AI / "state" / "project-state.yaml").read_text(encoding="utf-8"))
profile = yaml.safe_load((AI / "project-profile.yaml").read_text(encoding="utf-8")) or {}

print(t(LANG, "Project:", "Projet :") + f" {state.get('project_id')}")
print(t(LANG, "Phase:  ", "Phase :  ") + f" {state.get('phase')}")
try:
    from governed_ai.core.domain.run.autonomy_policy import resolve_project_preset

    preset = resolve_project_preset(profile.get("autonomy") or {})
except Exception:
    preset = (profile.get("autonomy") or {}).get("preset") or (profile.get("autonomy") or {}).get(
        "level"
    )
print(t(LANG, "Autonomy preset:", "Preset d'autonomie :") + f" {preset}")
print(t(LANG, "Gates:", "Gates :"))
for k, v in (state.get("gates") or {}).items():
    print(f"  {k}: {v.get('status') if isinstance(v, dict) else v}")

wus = []
for p in (AI / "work-units").glob("*.yaml"):
    try:
        wus.append(yaml.safe_load(p.read_text(encoding="utf-8")))
    except Exception:
        pass
if wus:
    c = Counter(w.get("status", "unknown") for w in wus)
    print(t(LANG, "Work Units:", "Unites de travail :"))
    for status, n in sorted(c.items()):
        print(f"  {status}: {n}")
else:
    print(t(LANG, "Work Units: none", "Unites de travail : aucune"))

print(t(LANG, "Open decisions:", "Decisions ouvertes :") + f" {len(state.get('open_decisions') or [])}")
print(t(LANG, "Open defects:  ", "Defauts ouverts :   ") + f" {len(state.get('open_defects') or [])}")
print(t(LANG, "Open findings: ", "Constats ouverts :  ") + f" {len(state.get('open_findings') or [])}")
active_workers = []
leases_dir = AI / "runs" / "leases"
if leases_dir.is_dir():
    for lease_path in leases_dir.glob("*.yaml"):
        try:
            lease = yaml.safe_load(lease_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if lease.get("status") == "active":
            active_workers.append(lease)
print(t(LANG, "Active workers:", "Agents actifs :     ") + f" {len(active_workers)}")
for lease in sorted(active_workers, key=lambda item: str(item.get("id"))):
    print(
        f"  {lease.get('worker_id')} run={lease.get('run_id')} "
        f"work_unit={lease.get('work_unit_id')} epoch={lease.get('epoch')}"
    )

runs_dir = AI / "runs"
active_or_recent_runs = []
if runs_dir.is_dir():
    for run_path in sorted(runs_dir.glob("*.yaml")):
        try:
            run = yaml.safe_load(run_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if run.get("status") in {"pending", "active", "completed", "stopped", "failed"}:
            active_or_recent_runs.append(run)
print(t(LANG, "Runs:", "Runs :") + f" {len(active_or_recent_runs)}")
for run in active_or_recent_runs:
    print(
        f"  {run.get('id')} status={run.get('status')} "
        f"preset={run.get('autonomy_preset')} stop={run.get('stop_condition')}"
    )
    if run.get("status") == "active":
        progress = evaluate_run_progress(AI, run)
        print(
            f"    progress={progress['state']} "
            f"last_progress={progress['last_progress_at']} "
            f"idle_minutes={progress['minutes_without_progress']}"
        )
    report_path = AI / "runs" / "morning-reports" / f"{run.get('id')}.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            print(
                t(LANG, "    morning report:", "    rapport matinal :")
                + (
                    f" completed={len(report.get('completed_work_units') or [])}"
                    f" paused={len(report.get('paused_work_units') or [])}"
                    f" cancelled={len(report.get('cancelled_work_units') or [])}"
                )
            )
        except (OSError, json.JSONDecodeError):
            pass

observations = []
for p in (AI / "observations").glob("*.yaml"):
    try:
        observations.append(yaml.safe_load(p.read_text(encoding="utf-8")) or {})
    except Exception:
        pass
unresolved = {"open", "acknowledged", "candidate_change"}
open_observations = [
    observation
    for observation in observations
    if observation.get("status") in unresolved
]
print(t(LANG, "Open observations:", "Constats d'apprentissage ouverts :") + f" {len(open_observations)}")
if open_observations:
    categories = Counter(
        observation.get("category", "unknown") for observation in open_observations
    )
    print(
        "  " + t(LANG, "by category: ", "par categorie : ")
        + ", ".join(f"{category}={count}" for category, count in sorted(categories.items()))
    )

checkpoints = {}
for p in sorted((AI / "events").glob("*.yaml")):
    try:
        event = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        continue
    if event.get("status") != "open":
        continue
    checkpoint = (event.get("details") or {}).get("human_checkpoint")
    if not checkpoint:
        continue
    # One line per Work Unit: keep the latest open checkpoint only.
    checkpoints[event.get("work_unit")] = (event.get("id"), checkpoint)
print(t(LANG, "Visual checkpoints available:", "Points de controle visuels disponibles :") + f" {len(checkpoints)}")
for work_unit, (event_id, checkpoint) in sorted(checkpoints.items(), key=lambda kv: kv[0] or ""):
    print(f"  {work_unit} ({event_id}): {checkpoint.get('command')}")
    print(f"    {checkpoint.get('why')}")
    if checkpoint.get("observed_revision"):
        print(f"    revision: {checkpoint.get('observed_revision')}")
    if checkpoint.get("acceptance_package_ref"):
        print(f"    scenarios: {checkpoint.get('acceptance_package_ref')}")

human_feedback = []
feedback_dir = AI / "human-feedback"
if feedback_dir.is_dir():
    for path in sorted(feedback_dir.glob("*.yaml")):
        try:
            human_feedback.append(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
        except Exception:
            pass
pending_human_feedback = [
    item for item in human_feedback if item.get("status") == "pending_reconciliation"
]
print(
    t(
        LANG,
        "Human feedback pending reconciliation:",
        "Retours humains a reconcilier :",
    )
    + f" {len(pending_human_feedback)}"
)
for item in pending_human_feedback:
    observed = item.get("observed_revision") or {}
    print(
        f"  {item.get('id')}: work_unit={item.get('work_unit')} "
        f"surface={item.get('surface')} observed={observed.get('commit_sha')}"
    )

smtp_status = public_smtp_status(load_smtp_settings(AI))
notification_records = []
for path in sorted((AI / "notifications").glob("NTF-*.json")):
    try:
        notification_records.append(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        pass
pending_notifications = [
    item for item in notification_records if item.get("status") in {"pending", "failed"}
]
smtp_label = "ready" if smtp_status["ready"] else "configuration_required"
if not smtp_status["enabled"]:
    smtp_label = "disabled"
print(t(LANG, "Email notifications:", "Notifications e-mail :") + f" {smtp_label}")
print(
    t(LANG, "Queued email notifications:", "Notifications e-mail en attente :")
    + f" {len(pending_notifications)}"
)

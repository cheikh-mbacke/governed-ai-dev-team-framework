#!/usr/bin/env python3
"""Answer 'is anything actually waiting on me, and what happened last?'

Run this before stopping and restarting anything. It never modifies state.
Core project diagnostics and Cursor hook diagnostics are separated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # noqa: F401 — dependency probe for PyYAML
except ModuleNotFoundError:
    _root = Path(__file__).resolve().parents[2]
    from install_paths import requirements_install_hint

    print("Missing dependency: PyYAML. Install it first, then re-run this command:")
    print(f"  {requirements_install_hint(_root)}")
    print("(or: pip install PyYAML jsonschema)")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[2]
from install_paths import bootstrap_runtime, import_adapters_cursor

bootstrap_runtime(ROOT)
_checks = import_adapters_cursor("runtime.checks")
last_hook_activity = _checks.last_hook_activity
from i18n import project_language, t

from governed_ai.core.diagnostics import (
    collect_in_flight_work_units,
    collect_open_human_events,
)

LANG = project_language(ROOT)


print(t(LANG, "Governed AI Team diagnosis", "Diagnostic Governed AI Team"))
print("=" * 26)
print()
print(t(
    LANG,
    "Before anything below: scroll up in the Cursor chat and check for a\n"
    "pending command-approval prompt (a 'Run' / 'Approve' button waiting\n"
    "for a click). This script cannot see that state - Cursor suspends the\n"
    "agent before it can write anything this script could read. It is the\n"
    "single most common invisible-stall cause; check it first.",
    "Avant toute chose : remontez dans le chat Cursor et cherchez une\n"
    "invite d'autorisation de commande en attente (un bouton 'Run' / 'Approve'\n"
    "qui attend un clic). Ce script ne peut pas voir cet etat - Cursor suspend\n"
    "l'agent avant qu'il puisse ecrire quoi que ce soit que ce script pourrait lire.\n"
    "C'est la cause de blocage invisible la plus frequente ; verifiez-la en premier.",
))

open_human_events = collect_open_human_events(ROOT)
if open_human_events:
    print("\n" + t(LANG, "ACTION NEEDED — open events waiting on a human:", "ACTION REQUISE - evenements ouverts en attente d'un humain :"))
    for fname, ev in open_human_events:
        no_summary = t(LANG, "(no summary)", "(pas de resume)")
        print(f"  [{ev.get('type', '?')}] {fname} — {ev.get('summary', no_summary)}")
        if ev.get("work_unit"):
            print("      " + t(LANG, "Work Unit:", "Work Unit :") + f" {ev['work_unit']}")
else:
    print("\n" + t(LANG, "No open event is explicitly marked as requiring human input.", "Aucun evenement ouvert n'est marque comme requerant explicitement un humain."))
    print(t(
        LANG,
        "If something still looks stuck, that itself is worth noting — see below.",
        "Si quelque chose semble quand meme bloque, c'est deja une information utile - voir plus bas.",
    ))

in_flight = collect_in_flight_work_units(ROOT)
if in_flight:
    print("\n" + t(LANG, "Work Units currently in flight (not ready, not done):", "Work Units actuellement en cours (ni pretes, ni terminees) :"))
    for wu_id, status in in_flight:
        print(f"  {wu_id}: {status}")

record = last_hook_activity(ROOT)
if record is None:
    print("\n" + t(
        LANG,
        "No .ai-team/logs/cursor-events.jsonl yet — no Cursor hook activity recorded.",
        "Pas encore de .ai-team/logs/cursor-events.jsonl - aucune activite Cursor (hook) enregistree.",
    ))
elif record.get("parse_error"):
    print("\n" + t(LANG, "Could not parse the last log line's timestamp.", "Impossible d'analyser l'horodatage de la derniere ligne du journal."))
else:
    ts = record.get("timestamp")
    if ts:
        last_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - last_dt
        minutes = int(delta.total_seconds() // 60)
        print("\n" + t(
            LANG,
            f"Last recorded Cursor hook activity: {minutes} minute(s) ago ({ts}).",
            f"Derniere activite Cursor (hook) enregistree : il y a {minutes} minute(s) ({ts}).",
        ))
        event_kind = None
        inner = record.get("event")
        if isinstance(inner, dict):
            event_kind = inner.get("hook_event_name") or inner.get("event")
        if event_kind:
            print("  " + t(LANG, f"(last event type: {event_kind})", f"(dernier type d'evenement : {event_kind})"))

print()
if open_human_events:
    print(t(
        LANG,
        "Next step: resolve the event(s) above, then continue — no need to restart anything.",
        "Prochaine etape : traiter le(s) evenement(s) ci-dessus, puis continuer - inutile de redemarrer quoi que ce soit.",
    ))
elif in_flight:
    print(t(
        LANG,
        "Next step: nothing is explicitly asking for you, but Work Units are mid-flight.",
        "Prochaine etape : rien ne vous sollicite explicitement, mais des Work Units sont en cours.",
    ))
    print(t(
        LANG,
        "If Cursor's own UI shows a subagent stalled with no recent hook activity above,\n"
        "that's a real stall with no recorded reason. See docs/OPERATOR_GUIDE.md\n"
        "(section 'If it looks stuck') before stopping/restarting.",
        "Si l'interface Cursor montre un subagent bloque sans activite (hook) recente ci-dessus,\n"
        "c'est un vrai blocage sans raison enregistree. Voir docs/OPERATOR_GUIDE.fr.md\n"
        "(section 'If it looks stuck') avant d'arreter/redemarrer quoi que ce soit.",
    ))
else:
    print(t(LANG, "Nothing appears in flight or waiting on you.", "Rien ne semble en cours ni en attente de votre part."))

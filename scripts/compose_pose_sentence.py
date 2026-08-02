#!/usr/bin/env python3
"""Compile a scored pose sentence without laundering visual acceptance.

The compiler proves references, role/grip compatibility, score ordering, and
interrupt routes. It reports missing runtime layers as a separate blocked
transition instead of treating a valid motion recipe as a finished animation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def atom_index(grammar: dict) -> dict[str, dict]:
    columns = grammar["pose_atom_columns"]
    return {row[0]: dict(zip(columns, row)) for row in grammar["pose_atoms"]}


def compile_sentence(grammar: dict, sentence: dict) -> dict:
    atoms = atom_index(grammar)
    failures: list[str] = []
    resolved: dict[str, dict] = {}

    for name, recipe in sentence["recipes"].items():
        atom_id = recipe["atom"]
        atom = atoms.get(atom_id)
        if atom is None:
            failures.append(f"{name}: unknown atom {atom_id}")
            continue
        expected = recipe["role"]
        actual = atom["role_hint"]
        override = recipe.get("accepted_role_override")
        if actual != expected and override != expected:
            failures.append(f"{name}: role {actual} does not satisfy {expected}")
        if override and not recipe.get("acceptance_authority"):
            failures.append(f"{name}: role override lacks acceptance authority")
        resolved[name] = {
            "atom": atom_id,
            "source_clip": atom["source_clip"],
            "sample_index": atom["sample_index"],
            "time_seconds": atom["time_seconds"],
            "role": expected,
            "catalog_role_hint": actual,
            "grip_class": atom["grip_class"],
            "status": recipe["status"],
        }

    grip_classes = {item["grip_class"] for item in resolved.values()}
    if len(grip_classes) > 1:
        failures.append(f"incompatible grip classes: {sorted(grip_classes)}")

    score = sentence["score"]
    allowed_events = set(grammar["score_language"]["events"])
    event_names = {event["event"] for event in score}
    for required in ("cue", "accent", "hold", "release", "stop"):
        if required not in event_names:
            failures.append(f"score missing {required}")
    previous = -1.0
    for event in score:
        if event["event"] not in allowed_events:
            failures.append(f"unsupported score event {event['event']}")
        if event["at_seconds"] < previous:
            failures.append("score events are not chronological")
        previous = event["at_seconds"]
        pose = event.get("pose")
        if pose is not None and pose not in resolved:
            failures.append(f"score references unknown recipe {pose}")

    for name in resolved:
        if name not in sentence["interrupts"]:
            failures.append(f"{name}: no interrupt route")
        elif sentence["interrupts"][name] not in resolved:
            failures.append(f"{name}: interrupt target is unknown")

    required_layers = grammar["laws"]["runtime_layers"]
    layer_failures: list[str] = []
    for name in resolved:
        supplied = sentence.get("layers", {}).get(name, {})
        for layer in required_layers:
            if not supplied.get(layer):
                layer_failures.append(f"{name}:{layer}")

    fps = sentence["authored_fps"]
    stop_time = max(event["at_seconds"] for event in score)
    frame_count = round(stop_time * fps) + 1
    current_pose = None
    timeline = []
    for frame in range(frame_count):
        at = round(frame / fps, 6)
        fired = [
            event for event in score
            if event["at_seconds"] <= at and event.get("pose") is not None
        ]
        if fired:
            current_pose = fired[-1]["pose"]
        timeline.append({"frame": frame, "at_seconds": at, "pose": current_pose})

    motion_status = "pass" if not failures else "blocked"
    visual_status = "blocked_missing_layers" if layer_failures else "ready_for_render"
    return {
        "schema": "fatal-vow.pose-sentence-compile/v1",
        "sentence_id": sentence["id"],
        "grammar_schema": grammar["schema"],
        "source_catalog_sha256": hashlib.sha256(canonical_bytes(grammar)).hexdigest(),
        "sentence_sha256": hashlib.sha256(canonical_bytes(sentence)).hexdigest(),
        "motion_compile_status": motion_status,
        "visual_compile_status": visual_status,
        "failures": failures,
        "missing_layers": layer_failures,
        "grip_class": next(iter(grip_classes)) if len(grip_classes) == 1 else None,
        "resolved_recipes": resolved,
        "score": score,
        "interrupts": sentence["interrupts"],
        "timeline": timeline,
        "claim_boundary": (
            "Motion/score compatibility may pass while visual runtime remains blocked. "
            "No watchdown or acceptance claim is permitted until every registered "
            "rear-hand, weapon, and foreground-finger layer exists."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("grammar", type=Path)
    parser.add_argument("sentence", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    compiled = compile_sentence(load(args.grammar), load(args.sentence))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(compiled, indent=2) + "\n")
    print(json.dumps({
        "motion_compile_status": compiled["motion_compile_status"],
        "visual_compile_status": compiled["visual_compile_status"],
        "missing_layers": len(compiled["missing_layers"]),
        "timeline_frames": len(compiled["timeline"]),
    }))


if __name__ == "__main__":
    main()

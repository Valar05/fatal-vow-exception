#!/usr/bin/env python3
"""Mine reusable pose atoms from the Fatal Vow motion corpus.

The miner does not declare artistic keys. It identifies source-exact candidate
poses using kinematic evidence, attaches conservative semantic hints, and emits
recipes that retain provenance back to the untouched motion corpus.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


FOCUS_WEIGHTS = {
    "Root": 0.5,
    "ShoulderCenter": 1.0,
    "Arm.L": 1.5,
    "Arm.R": 1.5,
    "Forearm.L": 2.0,
    "Forearm.R": 2.0,
    "Hand.L": 2.5,
    "Hand.R": 2.5,
    "Weapon.L": 3.0,
    "Weapon.R": 3.0,
    "UpperLeg": 0.75,
    "LowerLeg": 0.75,
    "Foot": 1.0,
    "Toe": 0.5,
}

ROLE_ANCHORS = {
    "attack": [
        (0.00, "guard"),
        (0.14, "anticipation"),
        (0.32, "commitment"),
        (0.50, "contact_candidate"),
        (0.64, "follow_through"),
        (0.76, "recoil"),
        (0.90, "recovery"),
        (1.00, "settle"),
    ],
    "defense": [
        (0.00, "guard"),
        (0.24, "brace"),
        (0.48, "impact_candidate"),
        (0.72, "absorb"),
        (1.00, "recovery"),
    ],
    "ready": [
        (0.00, "rest"),
        (0.30, "raise"),
        (0.65, "align"),
        (1.00, "readied"),
    ],
    "locomotion": [
        (0.00, "plant"),
        (0.25, "compression"),
        (0.50, "pass"),
        (0.75, "extension"),
        (1.00, "plant_return"),
    ],
    "air": [
        (0.00, "launch"),
        (0.25, "rise"),
        (0.50, "apex_candidate"),
        (0.75, "fall"),
        (1.00, "land_candidate"),
    ],
    "traversal": [
        (0.00, "approach"),
        (0.22, "reach"),
        (0.45, "contact_candidate"),
        (0.68, "pull_or_transfer"),
        (0.86, "clear"),
        (1.00, "settle"),
    ],
}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def quat_angle(a: list[float], b: list[float]) -> float:
    dot = abs(sum(x * y for x, y in zip(a, b)))
    return 2.0 * math.acos(clamp(dot, -1.0, 1.0))


def vector_distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def nlerp_quat(a: list[float], b: list[float], alpha: float) -> list[float]:
    if sum(x * y for x, y in zip(a, b)) < 0:
        b = [-x for x in b]
    out = [(1 - alpha) * x + alpha * y for x, y in zip(a, b)]
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]


def sample_channel(channel: dict, time_s: float) -> list[float]:
    times = channel["times_seconds"]
    values = channel["values"]
    if time_s <= times[0]:
        return values[0]
    if time_s >= times[-1]:
        return values[-1]
    hi = next(i for i, value in enumerate(times) if value >= time_s)
    lo = hi - 1
    if channel["interpolation"] == "STEP" or times[hi] == times[lo]:
        return values[lo]
    alpha = (time_s - times[lo]) / (times[hi] - times[lo])
    if channel["path"] == "rotation":
        return nlerp_quat(values[lo], values[hi], alpha)
    return [(1 - alpha) * a + alpha * b for a, b in zip(values[lo], values[hi])]


def focus_pose(clip: dict, time_s: float) -> dict[tuple[str, str], list[float]]:
    pose = {}
    for channel in clip["full_rig_channels"]:
        if channel["node"] in FOCUS_WEIGHTS:
            pose[(channel["node"], channel["path"])] = sample_channel(channel, time_s)
    return pose


def pose_delta(a: dict, b: dict) -> float:
    total = 0.0
    for key in a.keys() & b.keys():
        node, path = key
        weight = FOCUS_WEIGHTS[node]
        if path == "rotation":
            total += weight * quat_angle(a[key], b[key])
        elif path == "translation":
            total += weight * 2.0 * vector_distance(a[key], b[key])
    return total


def domain_for(category: str) -> str:
    if category == "fist_defense_hurt":
        return "defense"
    if category == "air_locomotion":
        return "air"
    if category == "locomotion":
        return "locomotion"
    if category == "traversal":
        return "traversal"
    if category.endswith("_ready"):
        return "ready"
    return "attack"


def grip_class(category: str) -> str:
    if category.startswith("one_hand"):
        return "one_hand_long_handle"
    if category.startswith("knife"):
        return "one_hand_short_handle"
    if category.startswith("wand"):
        return "one_hand_pointer"
    if category.startswith("fist"):
        return "unarmed"
    return "contextual"


def role_hint(domain: str, phase: float) -> str:
    anchors = ROLE_ANCHORS[domain]
    return min(anchors, key=lambda item: abs(item[0] - phase))[1]


def extrema_indices(samples: list[dict]) -> set[int]:
    indices: set[int] = set()
    for weapon_name in ("Weapon.R", "Weapon.L"):
        for axis in range(3):
            values = []
            for sample in samples:
                weapon = sample.get("weapons", {}).get(weapon_name)
                values.append(None if weapon is None else weapon["camera"]["translation"][axis])
            valid = [(i, value) for i, value in enumerate(values) if value is not None]
            if valid:
                indices.add(min(valid, key=lambda item: item[1])[0])
                indices.add(max(valid, key=lambda item: item[1])[0])
    return indices


def select_indices(
    clip: dict,
    maximum: int,
    domain: str,
) -> tuple[list[int], list[float], dict[int, set[str]]]:
    samples = clip["weapon_samples"]
    times = [sample["time_seconds"] for sample in samples]
    poses = [focus_pose(clip, value) for value in times]
    energy = [0.0] + [pose_delta(poses[i - 1], poses[i]) for i in range(1, len(poses))]
    reasons: dict[int, set[str]] = {0: {"endpoint"}, len(samples) - 1: {"endpoint"}}

    # Grammar coverage is a stronger contract than kinematic novelty. A clip
    # whose eight most interesting extrema omit recovery cannot compose even a
    # basic attack sentence. Pin the nearest source-exact sample for every role
    # anchor before filling the remaining budget with motion evidence.
    duration = clip["duration_seconds"] or 1.0
    required_indices: list[int] = []
    for anchor_phase, anchor_role in ROLE_ANCHORS[domain]:
        anchor_index = min(
            range(len(samples)),
            key=lambda index: abs((times[index] / duration) - anchor_phase),
        )
        reasons.setdefault(anchor_index, set()).add(f"phase_anchor:{anchor_role}")
        required_indices.append(anchor_index)

    required_unique = list(dict.fromkeys(required_indices))

    for index in extrema_indices(samples):
        reasons.setdefault(index, set()).add("weapon_camera_extremum")
    for index in range(1, len(energy) - 1):
        if energy[index] >= energy[index - 1] and energy[index] >= energy[index + 1]:
            reasons.setdefault(index, set()).add("local_motion_peak")
    ranked = sorted(reasons, key=lambda i: ("endpoint" in reasons[i], energy[i]), reverse=True)
    chosen: list[int] = []
    minimum_gap = 1 if len(samples) < 12 else 2
    for index in ranked:
        if index in (0, len(samples) - 1) or all(abs(index - other) >= minimum_gap for other in chosen):
            chosen.append(index)
        if len(chosen) >= maximum:
            break
    if len(chosen) < min(maximum, len(samples)):
        for index in sorted(range(len(samples)), key=lambda i: energy[i], reverse=True):
            if all(abs(index - other) >= minimum_gap for other in chosen):
                reasons.setdefault(index, set()).add("motion_energy")
                chosen.append(index)
            if len(chosen) >= maximum:
                break
    # maximum limits discovery atoms, not grammatical phase coverage.
    # Unioning the two preserves every previously interesting source witness
    # while guaranteeing that ordinary sentences remain typeable.
    return sorted(set(chosen) | set(required_unique)), energy, reasons


def build(corpus: dict, maximum: int) -> dict:
    atoms = []
    families: dict[str, list[str]] = {}
    for clip in corpus["clips"]:
        if not clip["weapon_samples"]:
            continue
        domain = domain_for(clip["category"])
        indices, energy, reasons = select_indices(clip, maximum, domain)
        duration = clip["duration_seconds"] or 1.0
        for index in indices:
            sample = clip["weapon_samples"][index]
            phase = sample["time_seconds"] / duration
            role = role_hint(domain, phase)
            atom_id = f"{slug(clip['name'])}.s{index:03d}"
            atom = {
                "id": atom_id,
                "status": "mined_candidate",
                "source": {
                    "clip": clip["name"],
                    "clip_category": clip["category"],
                    "sample_index": index,
                    "time_seconds": sample["time_seconds"],
                    "normalized_phase": round(phase, 6),
                    "transform_authority": "motion_corpus.json",
                },
                "classification": {
                    "domain": domain,
                    "role_hint": role,
                    "grip_class": grip_class(clip["category"]),
                    "selection_reasons": sorted(reasons.get(index, {"motion_energy"})),
                },
                "kinematic_salience": round(energy[index], 8),
                "weapon_registration": sample["weapons"],
                "reconstruction": {
                    "operation": "sample_source_pose",
                    "corpus_clip": clip["name"],
                    "time_seconds": sample["time_seconds"],
                    "preserve_native_channels": True,
                },
            }
            atoms.append(atom)
            families.setdefault(f"{domain}:{role}", []).append(atom_id)
    atom_columns = [
        "id",
        "status",
        "source_clip",
        "clip_category",
        "sample_index",
        "time_seconds",
        "normalized_phase",
        "domain",
        "role_hint",
        "grip_class",
        "selection_reasons",
        "kinematic_salience",
    ]
    atom_records = [
        [
            atom["id"],
            atom["status"],
            atom["source"]["clip"],
            atom["source"]["clip_category"],
            atom["source"]["sample_index"],
            atom["source"]["time_seconds"],
            atom["source"]["normalized_phase"],
            atom["classification"]["domain"],
            atom["classification"]["role_hint"],
            atom["classification"]["grip_class"],
            atom["classification"]["selection_reasons"],
            atom["kinematic_salience"],
        ]
        for atom in atoms
    ]
    return {
        "schema": "fatal-vow.pose-grammar.v0",
        "status": "mined_candidate_catalog",
        "source": {
            **corpus["source"],
            "corpus_schema": corpus["schema"],
            "clip_count": len(corpus["clips"]),
        },
        "laws": {
            "runtime_layers": ["rear_hand_forearm", "weapon", "front_fingers_knuckles"],
            "pose_recipe_operations": [
                "sample_source_pose",
                "copy_joint_subset",
                "apply_joint_override",
                "solve_declared_contact",
                "register_weapon_socket",
                "declare_occlusion",
                "render_candidate",
            ],
            "required_constraints": [
                "camera_mount",
                "grip_or_contact",
                "weapon_socket",
                "layer_occlusion",
                "frame_edge_exit",
                "source_provenance",
            ],
            "acceptance": "A composed pose remains candidate until rendered in the established FPS camera and visually accepted.",
        },
        "score_language": {
            "purpose": "Map authored beats or an audio timeline onto pose recipes without embedding pose identity in the song.",
            "events": ["cue", "accent", "hold", "release", "repeat", "interrupt", "transition", "stop"],
            "time_bases": ["seconds", "beats", "bars", "named_markers"],
            "rule": "The score may choose and time poses; it may not silently alter their contacts, provenance, or acceptance state.",
        },
        "pose_atom_count": len(atoms),
        "families": [{"id": key, "members": value} for key, value in sorted(families.items())],
        "pose_atom_columns": atom_columns,
        "pose_atoms": atom_records,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-per-clip", type=int, default=8)
    args = parser.parse_args()
    corpus = json.loads(args.corpus.read_text())
    grammar = build(corpus, max(2, args.max_per_clip))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(grammar, separators=(",", ":")) + "\n")
    print(json.dumps({"clips": grammar["source"]["clip_count"], "pose_atoms": grammar["pose_atom_count"], "families": len(grammar["families"])}))


if __name__ == "__main__":
    main()

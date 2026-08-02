#!/usr/bin/env python3
"""Validate the arm-independent weapon transform corpus against its donor GLB."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def glb_json(path: Path) -> dict:
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or length != len(data):
        raise ValueError("invalid GLB 2.0 source")
    json_length, json_type = struct.unpack_from("<I4s", data, 12)
    if json_type != b"JSON":
        raise ValueError("missing GLB JSON chunk")
    return json.loads(data[20 : 20 + json_length].decode("utf-8"))


def quaternion_distance(values: list[list[float]]) -> float:
    if not values:
        return 0.0
    first = values[0]
    return max(min(math.sqrt(sum((a - b) ** 2 for a, b in zip(first, value))), math.sqrt(sum((a + b) ** 2 for a, b in zip(first, value)))) for value in values)


def vector_range(values: list[list[float]]) -> float:
    if not values:
        return 0.0
    return max(max(row[column] for row in values) - min(row[column] for row in values) for column in range(len(values[0])))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--write-report", type=Path)
    args = parser.parse_args()

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    source = glb_json(args.source)
    failures: list[str] = []
    checks: list[str] = []

    def require(condition: bool, message: str) -> None:
        (checks if condition else failures).append(message)

    require(corpus.get("schema") == "fatal-vow.infinite-brutality-motion-corpus.v1", "corpus schema")
    require(digest(args.source) == corpus["source"]["source_sha256"], "source SHA-256")
    require(args.source.stat().st_size == corpus["source"]["source_bytes"], "source byte count")
    source_names = [animation.get("name") for animation in source.get("animations", [])]
    corpus_names = [clip.get("name") for clip in corpus.get("clips", [])]
    require(len(source_names) == 38, "source contains 38 clips")
    require(source_names == corpus_names, "source/corpus clip order and names")
    require(corpus["coordinate_basis"].get("quaternion_order") == "x,y,z,w", "declared quaternion order")

    inherited_motion = {}
    total_channels = 0
    for clip in corpus.get("clips", []):
        samples = clip.get("weapon_samples", [])
        times = [sample["time_seconds"] for sample in samples]
        require(len(samples) == clip.get("sample_count"), f"{clip['name']}: sample count")
        require(times == sorted(set(times)), f"{clip['name']}: unique monotonic native timeline")
        require(abs((times[-1] if times else 0.0) - clip.get("duration_seconds", 0.0)) < 1e-6, f"{clip['name']}: duration")
        total_channels += len(clip.get("full_rig_channels", []))
        for sample in samples:
            require(set(sample.get("weapons", {})) == {"Weapon.R", "Weapon.L"}, f"{clip['name']}: both weapon nodes")
            for weapon in sample.get("weapons", {}).values():
                for space in ("local", "model", "camera"):
                    quaternion = weapon[space]["rotation_xyzw"]
                    norm = math.sqrt(sum(value * value for value in quaternion))
                    require(abs(norm - 1.0) < 2e-5, f"{clip['name']}: normalized {space} quaternion")
        if clip["name"] in {"OneHandAttack1", "OneHandAttack2", "OneHandAttack3", "OneHandAttack4"}:
            local_positions = [sample["weapons"]["Weapon.R"]["local"]["translation"] for sample in samples]
            local_rotations = [sample["weapons"]["Weapon.R"]["local"]["rotation_xyzw"] for sample in samples]
            camera_positions = [sample["weapons"]["Weapon.R"]["camera"]["translation"] for sample in samples]
            camera_rotations = [sample["weapons"]["Weapon.R"]["camera"]["rotation_xyzw"] for sample in samples]
            inherited_motion[clip["name"]] = {
                "local_translation_range": round(vector_range(local_positions), 7),
                "local_rotation_distance": round(quaternion_distance(local_rotations), 7),
                "camera_translation_range": round(vector_range(camera_positions), 7),
                "camera_rotation_distance": round(quaternion_distance(camera_rotations), 7),
            }
            require(vector_range(camera_positions) > 0.01 or quaternion_distance(camera_rotations) > 0.05, f"{clip['name']}: visible inherited camera-space motion retained")

    duplicate = next((clip for clip in corpus["clips"] if clip["name"] == "OneHandAttack1.002"), None)
    require(duplicate is not None, "exporter duplicate retained")
    if duplicate:
        right_camera = [sample["weapons"]["Weapon.R"]["camera"]["translation"] for sample in duplicate["weapon_samples"]]
        require(len(duplicate["weapon_samples"]) == 2, "exporter duplicate endpoint samples retained")
        require(vector_range(right_camera) < 1e-6, "exporter duplicate correctly flagged static")

    report = {
        "schema": "fatal-vow.weapon-motion-validation.v1",
        "status": "PASS" if not failures else "FAIL",
        "authority": "source/reference only; no human animation acceptance implied",
        "source_sha256": digest(args.source),
        "corpus_sha256": digest(args.corpus),
        "clip_count": len(corpus.get("clips", [])),
        "full_rig_channel_count": total_channels,
        "weapon_nodes": ["Weapon.R", "Weapon.L"],
        "arm_free_runtime_track": "camera-space Weapon.R translation/quaternion/scale samples",
        "inherited_motion_evidence": inherited_motion,
        "retained_exporter_fossil": {
            "clip": "OneHandAttack1.002",
            "duration_seconds": duplicate.get("duration_seconds") if duplicate else None,
            "sample_count": duplicate.get("sample_count") if duplicate else None,
            "classification": "static duplicate; retained and not promoted",
        },
        "checks_passed": len(checks),
        "failures": failures,
    }
    output = json.dumps(report, indent=2) + "\n"
    if args.write_report:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(output, encoding="utf-8")
    print(output, end="")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

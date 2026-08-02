#!/usr/bin/env python3
"""Build an immutable source-locked OneHandAttack2 + shovel review packet."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


CPU_RENDERER = Path("/root/.codex/skills/remote-skills/skill-6a64df8937e08191ac93c3d26d221262/scripts/render_glb_cpu.py")
FPS_RENDERER = Path(__file__).with_name("render_fps_family.py")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


glb = load_module("fatal_vow_glb_cpu", CPU_RENDERER)
fps = load_module("fatal_vow_fps_render", FPS_RENDERER)


KEYS = [
    ("k001", 0.000000, "guarded start"),
    ("k002", 0.083333, "anticipation begins"),
    ("k003", 0.208333, "left crossing extreme"),
    ("k004", 0.250000, "fast re-entry and reversal"),
    ("k005", 0.333333, "rightward catch"),
    ("k006", 0.625000, "high-right reach extreme"),
    ("k007", 0.791667, "recovery landing"),
    ("k008", 1.250000, "held endpoint"),
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def shovel_geometry(source: Path):
    doc, binary = glb.load_glb(source)
    asset = glb.Asset(source, doc, binary, {}, 0.0, 0.0)
    geometry = glb.geometry(asset, 0.0, "material")
    selected = []
    # The shovel is the upper-left prop in the accepted atlas XY layout.
    xmin, xmax = -0.50, -0.25
    ymin, ymax = 0.145, 0.380
    for positions, triangles, colors in geometry:
        centroids = positions[triangles].mean(axis=1)
        keep = (
            (centroids[:, 0] >= xmin)
            & (centroids[:, 0] <= xmax)
            & (centroids[:, 1] >= ymin)
            & (centroids[:, 1] <= ymax)
        )
        if np.any(keep):
            selected.append((positions, triangles[keep], colors))
    if not selected:
        raise ValueError("Shovel atlas region selected no triangles")
    return selected


def attach_shovel(source_geometry, weapon_matrix, scale=3.8):
    # Grip witness is the upper-right end of the shovel shaft in atlas XY.
    grip = np.array([-0.272, 0.352, 0.0], dtype=np.float64)
    blade = np.array([-0.395, 0.195, 0.0], dtype=np.float64)
    shaft = blade - grip
    shaft /= np.linalg.norm(shaft)
    local_x = np.array([-shaft[1], shaft[0], 0.0], dtype=np.float64)
    local_y = shaft
    local_z = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    # Donor weapon overlays establish socket +Z (blue), not +Y (green), as the
    # longitudinal weapon path. Preserve shovel breadth on socket X and map the
    # atlas thickness to socket Y so the head remains readable without crossing
    # through the camera during the recovery.
    source_to_socket = np.stack([local_x, local_z, local_y], axis=1)
    result = []
    for positions, triangles, colors in source_geometry:
        local = (positions - grip) @ source_to_socket
        local *= scale
        hom = np.concatenate([local, np.ones((len(local), 1))], axis=1)
        world = (weapon_matrix @ hom.T).T[:, :3]
        result.append((world, triangles, colors))
    return result


def label(frame: Image.Image, text: str) -> Image.Image:
    out = frame.copy()
    draw = ImageDraw.Draw(out)
    font = ImageFont.load_default()
    draw.rectangle((0, 0, out.width, 20), fill=(3, 5, 7))
    draw.text((7, 5), text, fill=(245, 245, 245), font=font)
    return out


def make_sheet(frames, output: Path, columns=4, labels=None):
    width, height = frames[0].size
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new("RGB", (columns * width, rows * height), (8, 10, 13))
    for index, frame in enumerate(frames):
        cell = label(frame, labels[index]) if labels else frame
        sheet.paste(cell, ((index % columns) * width, (index // columns) * height))
    sheet.save(output)


def projected_weapon_record(asset, at, camera_index, weapon_index, width, height, fov):
    matrices = glb.global_matrices(asset, at)
    matrix = matrices[weapon_index]
    origin = matrix[:3, 3]
    y_axis = matrix[:3, 1] / max(np.linalg.norm(matrix[:3, 1]), 1e-9)
    points = fps.project(
        np.stack([origin, origin + y_axis * 0.70]),
        fps.camera_basis(asset, at, camera_index),
        width,
        height,
        fov,
    )
    return {
        "socket_screen_xy": [round(float(x), 3) for x in points[0, :2]],
        "shaft_witness_screen_xy": [round(float(x), 3) for x in points[1, :2]],
        "socket_model_xyz": [round(float(x), 7) for x in origin],
        "socket_rotation_matrix": [[round(float(x), 7) for x in row] for row in matrix[:3, :3]],
        "shaft_endpoint_visibility": "visible" if points[1, 2] > 0.001 else "behind-camera",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arms_glb", type=Path)
    parser.add_argument("prop_glb", type=Path)
    parser.add_argument("identity_plate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--fov", type=float, default=82.0)
    args = parser.parse_args()

    packet = args.output
    source_dir = packet / "source"
    sheet_dir = packet / "sheets"
    identity_dir = packet / "identity" / "references"
    runtime_dir = packet / "runtime"
    for path in (source_dir, sheet_dir, identity_dir, runtime_dir):
        path.mkdir(parents=True, exist_ok=True)

    asset, _ = glb.load_asset(args.arms_glb, "OneHandAttack2")
    camera_index = fps.camera_index(asset)
    weapon_matches = [i for i, node in enumerate(asset.doc["nodes"]) if node.get("name") == "Weapon.R"]
    if len(weapon_matches) != 1:
        raise ValueError(f"Expected one Weapon.R; found {len(weapon_matches)}")
    weapon_index = weapon_matches[0]
    shovel = shovel_geometry(args.prop_glb)

    frames = []
    records = []
    source_frame_dir = source_dir / "frames"
    source_frame_dir.mkdir(exist_ok=True)
    for key_id, at, event in KEYS:
        basis = fps.camera_basis(asset, at, camera_index)
        arm_geometry = glb.geometry(asset, at, "material")
        weapon_matrix = glb.global_matrices(asset, at)[weapon_index]
        coupled = arm_geometry + attach_shovel(shovel, weapon_matrix)
        frame = fps.rasterize(coupled, basis, args.width, args.height, args.fov)
        frame_path = source_frame_dir / f"{key_id}.png"
        frame.save(frame_path)
        frames.append(frame)
        duration = 0.0
        records.append({
            "id": key_id,
            "source_index": int(round(at * 24)),
            "time_seconds": at,
            "duration_seconds": duration,
            "event": event,
            "path": str(frame_path.relative_to(packet)),
            "sha256": sha256(frame_path),
            "weapon": projected_weapon_record(asset, at, camera_index, weapon_index, args.width, args.height, args.fov),
        })
    for index, record in enumerate(records):
        next_time = records[index + 1]["time_seconds"] if index + 1 < len(records) else 1.25 + 1 / 24
        record["duration_seconds"] = round(next_time - record["time_seconds"], 6)

    make_sheet(frames, sheet_dir / "motion-input.png", columns=4)
    # A 3x3 grid of 16:9 cells is itself 16:9. The ninth cell remains an
    # immutable empty plate so image generation need not squeeze the source
    # cameras to fit an ultra-wide 4x2 canvas.
    make_sheet(frames, sheet_dir / "motion-input-3x3.png", columns=3)
    make_sheet(
        frames,
        sheet_dir / "motion-review.png",
        columns=4,
        labels=[f"{key_id}  {at:.3f}s  {event}" for key_id, at, event in KEYS],
    )
    make_sheet(
        frames,
        sheet_dir / "motion-review-3x3.png",
        columns=3,
        labels=[f"{key_id}  {at:.3f}s  {event}" for key_id, at, event in KEYS],
    )
    frames[3].save(sheet_dir / "load-bearing-k004.png")
    args.identity_plate.replace(identity_dir / args.identity_plate.name) if False else None

    motion = {
        "schema": "rotoscoping.motion/v1",
        "project_id": "fatal-vow-onehandattack2-shovel-v3",
        "product_invariant": "candidate motion = source motion; candidate identity = accepted target identity",
        "source": {
            "name": args.arms_glb.name,
            "sha256": sha256(args.arms_glb),
            "ownership": "project-owned or user-authorized Infinite Brutality donor asset",
            "clip": "OneHandAttack2",
            "frame_rate": 24.0,
            "duration_seconds": 1.25,
            "display_width": args.width,
            "display_height": args.height,
            "audio": "none",
        },
        "prop": {
            "name": args.prop_glb.name,
            "sha256": sha256(args.prop_glb),
            "atlas_region_xy": [-0.50, 0.145, -0.25, 0.380],
            "socket": "Weapon.R",
            "registration": "candidate; source-locked socket path with authored shovel-to-socket bind",
        },
        "motion": {"keyframes": records},
        "locks": {
            "camera": "Infinite Brutality arms runtime: vertical FOV 82 degrees, 16:9, Camera node + (0, 0.015, 0), look +Z",
            "anchor": "fixed source camera and per-key Weapon.R socket",
            "direction": "source screen direction; no mirror",
            "identity": "Medieval Fleshpunk Hand Turnaround Sheet; full forearms and tapered cloth terminations",
            "timing": "source key timestamps; authored exposure revision prohibited before key-only approval",
            "background": "flat dark diagnostic plate",
        },
        "selection": {
            "status": "reviewed-source-proposal",
            "policy": "preserve start, release, crossing extreme, reversal, reach extreme, recovery, and held endpoint",
        },
    }
    (source_dir / "motion.json").write_text(json.dumps(motion, indent=2) + "\n", encoding="utf-8")

    evidence = {
        "schema": "fatal-vow.source-evidence/v1",
        "source_motion": "OneHandAttack2",
        "visibility_policy": "Only visible source events are asserted; hidden finger closure is unknown.",
        "events": [
            {"key_id": r["id"], "time_seconds": r["time_seconds"], "event": r["event"], "right_hand_to_tool": "Weapon.R socket locked", "left_hand_attachment": "not attached", "finger_closure": "unknown from donor mesh", "weapon_root": r["weapon"]["socket_screen_xy"], "weapon_shaft_witness": r["weapon"]["shaft_witness_screen_xy"], "support_feet": "not applicable in first-person arm crop"}
            for r in records
        ],
        "critical_key": "k004",
        "critical_reason": "fast re-entry plus weapon reversal, grip foreshortening, and broad silhouette change",
    }
    (source_dir / "source-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    ledger = {
        "schema": "rotoscoping.constraint-ledger/v1",
        "constraints": [
            {"id": "c001", "statement": "Use OneHandAttack2 pose order and timing as immutable motion authority.", "status": "locked"},
            {"id": "c002", "statement": "Use the accepted Medieval Fleshpunk Hand Turnaround Sheet as identity authority.", "status": "locked"},
            {"id": "c003", "statement": "Render full lateral forearm silhouettes with no square sleeve cutoffs.", "status": "locked"},
            {"id": "c004", "statement": "Keep hand, forearm, grip, and shovel as one coupled performance.", "status": "locked"},
            {"id": "c005", "statement": "No in-betweens or timing polish before key-only runtime approval.", "status": "locked"},
            {"id": "c006", "statement": "Shovel-to-socket bind is candidate until human review.", "status": "open"},
        ],
    }
    (packet / "constraint-ledger.json").write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")

    identity_lock = """# Fatal Vow first-person hand identity lock\n\n- Authority: Medieval Fleshpunk Hand Turnaround Sheet.png\n- Preserve rugged medieval flesh, broad knuckles, natural five-finger anatomy, wrapped leather wrist/cuff, and tapered cloth forearm terminations.\n- Show complete lateral forearm silhouettes where the source crop permits; never terminate a sleeve with a square artificial cutoff.\n- Do not import the donor mesh's generic hand design.\n- Grip closure must wrap the shovel shaft without fused, detached, duplicated, or reversed fingers.\n- The plate defines appearance only. Weapon socket motion and pose order remain source authority.\n"""
    (packet / "identity" / "identity-lock.md").write_text(identity_lock, encoding="utf-8")

    review_regions = {
        "schema": "rotoscoping.review-regions/v1",
        "keys": {
            r["id"]: {
                "hands-grip": [max(0, int(r["weapon"]["socket_screen_xy"][0] - 90)), max(0, int(r["weapon"]["socket_screen_xy"][1] - 90)), 180, 180],
                "weapon": [0, 0, args.width, args.height],
                "root": [0, 0, args.width, args.height],
            }
            for r in records
        },
    }
    (runtime_dir / "review-regions.json").write_text(json.dumps(review_regions, indent=2) + "\n", encoding="utf-8")

    packet_manifest = {
        "schema": "fatal-vow.motion-packet/v1",
        "job_id": "fatal-vow-onehandattack2-shovel-v3",
        "source_sha256": sha256(args.arms_glb),
        "prop_sha256": sha256(args.prop_glb),
        "identity_sha256": sha256(args.identity_plate),
        "key_count": len(records),
        "critical_key": "k004",
        "status": "source-locked candidate packet; identity transfer unjudged",
    }
    (packet / "packet-manifest.json").write_text(json.dumps(packet_manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "packet": str(packet), "keys": len(records)}))


if __name__ == "__main__":
    main()

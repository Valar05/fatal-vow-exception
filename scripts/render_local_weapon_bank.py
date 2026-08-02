#!/usr/bin/env python3
"""Render the Fatal Vow shovel bank locally with semantic vertex colors.

This deliberately narrow renderer consumes the approved prop-atlas GLB and the
source-exact camera-space Weapon.R transforms retained by pose_grammar.v1.json.
It does not call Blender, WebGL, Home Center rendering, or an image generator.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
FORMATS = {
    5120: (np.int8, 1),
    5121: (np.uint8, 1),
    5122: (np.int16, 2),
    5123: (np.uint16, 2),
    5125: (np.uint32, 4),
    5126: (np.float32, 4),
}
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

# These are the four recipes in onehandattack2-minimal-grammar-proof-v0.
ATOM_ORDER = (
    ("onehandattack2.s000", "guard"),
    ("onehandattack2.s004", "anticipation"),
    ("onehandattack2.s006", "contact"),
    ("onehandattack2.s027", "recovery"),
)

# Fixed Infinite Brutality FPS camera contract recovered from the authoritative
# source review: vertical FOV 82 degrees, 16:9, Camera node plus (0,.015,0),
# looking along world +Z. Screen-right is world -X.
WIDTH = 640
HEIGHT = 360
CX = WIDTH / 2
CY = HEIGHT / 2
FOCAL = HEIGHT / (2.0 * math.tan(math.radians(82.0) / 2.0))
CAMERA_ORIGIN = np.array([0.0, 1.2680411338806152 + 0.015, -0.0392589196562767])
NEAR = 0.015


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_glb(path: Path) -> tuple[dict, bytes]:
    payload = path.read_bytes()
    magic, version, total = struct.unpack_from("<4sII", payload, 0)
    if magic != b"glTF" or version != 2 or total != len(payload):
        raise ValueError(f"{path} is not a valid binary glTF 2.0 file")
    chunks: dict[int, bytes] = {}
    offset = 12
    while offset < total:
        length, kind = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunks[kind] = payload[offset : offset + length]
        offset += length
    if JSON_CHUNK not in chunks or BIN_CHUNK not in chunks:
        raise ValueError("GLB must contain JSON and BIN chunks")
    return json.loads(chunks[JSON_CHUNK]), chunks[BIN_CHUNK]


def accessor(doc: dict, binary: bytes, index: int) -> np.ndarray:
    item = doc["accessors"][index]
    if item.get("sparse"):
        raise ValueError("Sparse accessors are unsupported")
    view = doc["bufferViews"][item["bufferView"]]
    dtype, size = FORMATS[item["componentType"]]
    width = COMPONENTS[item["type"]]
    stride = view.get("byteStride", size * width)
    start = view.get("byteOffset", 0) + item.get("byteOffset", 0)
    if stride == size * width:
        values = np.frombuffer(
            binary, dtype=dtype, count=item["count"] * width, offset=start
        ).reshape(item["count"], width)
    else:
        values = np.empty((item["count"], width), dtype=dtype)
        for row in range(item["count"]):
            byte_start = start + row * stride
            values[row] = np.frombuffer(
                binary, dtype=dtype, count=width, offset=byte_start
            )
    return values


def quat_matrix(value: list[float]) -> np.ndarray:
    x, y, z, w = np.asarray(value, dtype=np.float64)
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length < 1e-12:
        raise ValueError("Zero-length quaternion")
    x, y, z, w = x / length, y / length, z / length, w / length
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), 0],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), 0],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), 0],
            [0, 0, 0, 1],
        ],
        dtype=np.float64,
    )


def trs_matrix(record: dict) -> np.ndarray:
    result = quat_matrix(record["rotation_xyzw"])
    result[:3, :3] *= np.asarray(record["scale"], dtype=np.float64)[None, :]
    result[:3, 3] = np.asarray(record["translation"], dtype=np.float64)
    return result


def extract_shovel(glb_path: Path):
    doc, binary = load_glb(glb_path)
    if len(doc.get("meshes", [])) != 1:
        raise ValueError("Expected the approved prop atlas to contain one mesh")
    primitive = doc["meshes"][0]["primitives"][0]
    if primitive.get("mode", 4) != 4:
        raise ValueError("Expected triangle geometry")
    positions = accessor(doc, binary, primitive["attributes"]["POSITION"]).astype(
        np.float64
    )
    triangles = accessor(doc, binary, primitive["indices"]).reshape(-1, 3).astype(
        np.int64
    )

    # The atlas is a fixed 4x3 spatial layout. This bounded region is the
    # visually reviewed top-left shovel, not a semantic guess from component
    # size or filename.
    points = positions[triangles]
    centroids = points.mean(axis=1)
    selected = (
        (centroids[:, 0] >= -0.50)
        & (centroids[:, 0] <= -0.25)
        & (centroids[:, 1] >= 0.145)
        & (centroids[:, 1] <= 0.380)
    )
    triangles = triangles[selected]
    if len(triangles) != 182:
        raise ValueError(f"Shovel extraction drifted: expected 182 triangles, got {len(triangles)}")
    indices = np.unique(triangles)
    remap = np.full(len(positions), -1, dtype=np.int64)
    remap[indices] = np.arange(len(indices))
    positions = positions[indices]
    triangles = remap[triangles]

    # Canonical long-handle contract: origin at the lower handle, +Z toward
    # the shovel blade. X crosses the shallow tool thickness.
    grip_origin = np.array([-0.272, 0.352, 0.0], dtype=np.float64)
    blade_center = np.array([-0.395, 0.195, 0.0], dtype=np.float64)
    shaft = blade_center - grip_origin
    shaft /= np.linalg.norm(shaft)
    transverse = np.array([-shaft[1], shaft[0], 0.0], dtype=np.float64)
    thickness = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    # Atlas transverse -> socket X; atlas thickness -> socket Y; atlas shaft
    # toward blade -> socket +Z. This is the accepted replacement for +Y bind.
    source_to_socket = np.stack([transverse, thickness, shaft], axis=1)
    local_positions = (positions - grip_origin) @ source_to_socket
    source_extent = float(local_positions[:, 2].max() - local_positions[:, 2].min())
    scale = 3.8
    target_extent = source_extent * scale
    local_positions *= scale

    # Semantic vertex color, not texture: magenta grip, cyan shaft, blue blade.
    normalized = (local_positions[:, 2] - local_positions[:, 2].min()) / (
        local_positions[:, 2].max() - local_positions[:, 2].min()
    )
    colors = np.empty((len(local_positions), 3), dtype=np.float64)
    grip = normalized < 0.22
    shaft = (normalized >= 0.22) & (normalized < 0.68)
    blade = normalized >= 0.68
    colors[grip] = [232, 82, 196]
    colors[shaft] = [72, 214, 191]
    colors[blade] = [91, 149, 238]
    return local_positions, triangles, colors, {
        "selection": {"x_lt": -0.24, "y_gt": 0.10, "triangles": int(len(triangles))},
        "grip_origin_atlas": grip_origin.tolist(),
        "local_axes_atlas": {
            "x": transverse.tolist(),
            "y": thickness.tolist(),
            "z_toward_blade": shaft.tolist(),
        },
        "source_extent": source_extent,
        "target_extent": target_extent,
        "uniform_scale": scale,
        "vertex_color_contract": {
            "grip": "#E852C4",
            "shaft": "#48D6BF",
            "blade": "#5B95EE",
        },
    }


def atom_rows(catalog: dict) -> dict[str, dict]:
    columns = catalog["pose_atom_columns"]
    rows = {row[0]: dict(zip(columns, row)) for row in catalog["pose_atoms"]}
    result = {}
    for atom, _ in ATOM_ORDER:
        if atom not in rows:
            raise ValueError(f"Missing exact pose atom {atom}")
        result[atom] = rows[atom]
    return result


def project(points: np.ndarray) -> np.ndarray:
    camera = points - CAMERA_ORIGIN
    depth = camera[:, 2]
    pixels = np.empty_like(points)
    pixels[:, 0] = CX - FOCAL * camera[:, 0] / depth
    pixels[:, 1] = CY - FOCAL * camera[:, 1] / depth
    pixels[:, 2] = depth
    return pixels


def rasterize_many(geometry) -> tuple[Image.Image, np.ndarray]:
    canvas = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    depth_buffer = np.full((HEIGHT, WIDTH), np.inf, dtype=np.float64)
    for points, triangles, colors in geometry:
        projected = project(points)
        for triangle in triangles:
            camera_triangle = points[triangle]
            if np.any((camera_triangle - CAMERA_ORIGIN)[:, 2] <= NEAR):
                continue
            p = projected[triangle]
            min_x = max(0, int(math.floor(np.min(p[:, 0]))))
            max_x = min(WIDTH - 1, int(math.ceil(np.max(p[:, 0]))))
            min_y = max(0, int(math.floor(np.min(p[:, 1]))))
            max_y = min(HEIGHT - 1, int(math.ceil(np.max(p[:, 1]))))
            if min_x > max_x or min_y > max_y:
                continue
            first, second, third = p
            area = (second[1] - third[1]) * (first[0] - third[0]) + (
                third[0] - second[0]
            ) * (first[1] - third[1])
            if abs(area) < 1e-10:
                continue
            xs = np.arange(min_x, max_x + 1, dtype=np.float64) + 0.5
            ys = np.arange(min_y, max_y + 1, dtype=np.float64) + 0.5
            xx, yy = np.meshgrid(xs, ys)
            w0 = (
                (second[1] - third[1]) * (xx - third[0])
                + (third[0] - second[0]) * (yy - third[1])
            ) / area
            w1 = (
                (third[1] - first[1]) * (xx - third[0])
                + (first[0] - third[0]) * (yy - third[1])
            ) / area
            w2 = 1.0 - w0 - w1
            inside = (w0 >= -1e-8) & (w1 >= -1e-8) & (w2 >= -1e-8)
            reciprocal = w0 / first[2] + w1 / second[2] + w2 / third[2]
            z = np.where(reciprocal > 1e-12, 1.0 / reciprocal, np.inf)
            current = depth_buffer[min_y : max_y + 1, min_x : max_x + 1]
            update = inside & (z < current)
            if not np.any(update):
                continue
            triangle_colors = colors[triangle]
            color = np.clip(
                w0[..., None] * triangle_colors[0]
                + w1[..., None] * triangle_colors[1]
                + w2[..., None] * triangle_colors[2],
                0,
                255,
            ).astype(np.uint8)
            current[update] = z[update]
            target = canvas[min_y : max_y + 1, min_x : max_x + 1]
            target[update, :3] = color[update]
            target[update, 3] = 255
    return Image.fromarray(canvas, "RGBA"), depth_buffer


def dark_review(frame: Image.Image) -> Image.Image:
    background = Image.new("RGBA", frame.size, (10, 13, 18, 255))
    background.alpha_composite(frame)
    return background.convert("RGB")


def contact_sheet(frames: list[Image.Image], labels: list[str]) -> Image.Image:
    sheet = Image.new("RGB", (WIDTH * 2, HEIGHT * 2), (10, 13, 18))
    font = ImageFont.load_default()
    for index, (frame, label_text) in enumerate(zip(frames, labels)):
        review = dark_review(frame)
        draw = ImageDraw.Draw(review)
        draw.rectangle((0, 0, WIDTH, 24), fill=(3, 5, 8))
        draw.text((8, 7), label_text, fill=(245, 245, 245), font=font)
        sheet.paste(review, ((index % 2) * WIDTH, (index // 2) * HEIGHT))
    return sheet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--arms", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--cpu-renderer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    frames_dir = args.output / "frames"
    frames_dir.mkdir(exist_ok=True)

    catalog = json.loads(args.catalog.read_text())
    rows = atom_rows(catalog)
    spec = importlib.util.spec_from_file_location("fatal_vow_glb_cpu", args.cpu_renderer)
    glb_cpu = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise ValueError("Could not load the local CPU GLB renderer")
    sys.modules["fatal_vow_glb_cpu"] = glb_cpu
    spec.loader.exec_module(glb_cpu)
    arms_asset, _ = glb_cpu.load_asset(args.arms, "OneHandAttack2")
    local_positions, triangles, colors, extraction = extract_shovel(args.atlas)
    source_homogeneous = np.concatenate(
        [local_positions, np.ones((len(local_positions), 1))], axis=1
    )

    frames: list[Image.Image] = []
    composite_frames: list[Image.Image] = []
    labels: list[str] = []
    frame_records = []
    for index, (atom, role) in enumerate(ATOM_ORDER):
        row = rows[atom]
        socket = row["weapon_registration"]["Weapon.R"]["model"]
        model_points = (trs_matrix(socket) @ source_homogeneous.T).T[:, :3]
        weapon_geometry = [(model_points, triangles, colors)]
        frame, depth = rasterize_many(weapon_geometry)
        arm_geometry = glb_cpu.geometry(
            arms_asset, float(row["time_seconds"]), "bone-heat"
        )
        composite, _ = rasterize_many(arm_geometry + weapon_geometry)
        alpha = np.asarray(frame)[:, :, 3]
        if not np.any(alpha):
            raise ValueError(f"{atom} produced a blank local render")
        frame_path = frames_dir / f"{index:02d}-{role}.png"
        frame.save(frame_path)
        composite_path = frames_dir / f"{index:02d}-{role}-vertex-color-composite.png"
        composite.save(composite_path)
        frames.append(frame)
        composite_frames.append(composite)
        labels.append(f"{atom} · {role} · {row['time_seconds']:.7f}s")
        ys, xs = np.nonzero(alpha)
        frame_records.append(
            {
                "atom": atom,
                "role": role,
                "sample_index": row["sample_index"],
                "time_seconds": row["time_seconds"],
                "weapon_r_model": socket,
                "output": str(frame_path.relative_to(args.output)),
                "sha256": sha256(frame_path),
                "vertex_color_composite": str(composite_path.relative_to(args.output)),
                "vertex_color_composite_sha256": sha256(composite_path),
                "visible_bounds_px": [
                    int(xs.min()),
                    int(ys.min()),
                    int(xs.max()),
                    int(ys.max()),
                ],
                "touches_boundary": bool(
                    xs.min() == 0
                    or ys.min() == 0
                    or xs.max() == WIDTH - 1
                    or ys.max() == HEIGHT - 1
                ),
                "nearest_visible_depth": float(np.min(depth[np.isfinite(depth)])),
            }
        )

    sheet_path = args.output / "onehandattack2-weapon-bank-contact-sheet.png"
    contact_sheet(frames, labels).save(sheet_path)
    composite_sheet_path = args.output / "onehandattack2-vertex-color-composite-contact-sheet.png"
    contact_sheet(composite_frames, labels).save(composite_sheet_path)

    # cue, anticipation, contact accent+hold, then four recovery exposures.
    timeline = [0, 1, 2, 2, 3, 3, 3, 3]
    gif_frames = [dark_review(frames[index]) for index in timeline]
    gif_path = args.output / "onehandattack2-weapon-bank-watchdown.gif"
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=[100] * len(gif_frames),
        loop=0,
        disposal=2,
    )
    composite_gif_frames = [dark_review(composite_frames[index]) for index in timeline]
    composite_gif_path = args.output / "onehandattack2-vertex-color-composite-watchdown.gif"
    composite_gif_frames[0].save(
        composite_gif_path,
        save_all=True,
        append_images=composite_gif_frames[1:],
        duration=[100] * len(composite_gif_frames),
        loop=0,
        disposal=2,
    )

    manifest = {
        "schema": "fatal-vow.local-vertex-color-weapon-bank/v1",
        "status": "candidate_visual_evidence",
        "renderer": "scripts/render_local_weapon_bank.py",
        "authorized_lane": "local_only",
        "source_atlas": {
            "filename": args.atlas.name,
            "sha256": sha256(args.atlas),
            **extraction,
        },
        "pose_catalog": {
            "filename": args.catalog.name,
            "sha256": sha256(args.catalog),
        },
        "arms_source": {
            "filename": args.arms.name,
            "sha256": sha256(args.arms),
            "vertex_color_mode": "bone-heat from actual skin weights",
        },
        "camera": {
            "canvas": [WIDTH, HEIGHT],
            "projection": "u=CX-focal*(world_x-origin_x)/depth; v=CY-focal*(world_y-origin_y)/depth; depth=world_z-origin_z",
            "cx": CX,
            "cy": CY,
            "vertical_fov_degrees": 82.0,
            "focal": FOCAL,
            "origin_world": CAMERA_ORIGIN.tolist(),
            "forward_world": "+Z",
            "near": NEAR,
            "calibration_source": "docs/ONEHANDATTACK2_SHOVEL_SOURCE_REVIEW.md and source GLB Camera node",
        },
        "frames": frame_records,
        "watchdown": {
            "timeline_frame_indices": timeline,
            "durations_ms": [100] * len(timeline),
            "output": gif_path.name,
            "vertex_color_composite_output": composite_gif_path.name,
        },
        "contact_sheet": sheet_path.name,
        "vertex_color_composite_contact_sheet": composite_sheet_path.name,
        "claim_boundary": (
            "This proves local source-atlas extraction, semantic vertex coloring, "
            "camera-space Weapon.R registration, and weapon-only cadence. It does "
            "not prove accepted hand identity, grip closure, or final occlusion."
        ),
    }
    manifest_path = args.output / "onehandattack2-local-weapon-bank.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "frames": 4, "manifest": str(manifest_path)}))


if __name__ == "__main__":
    main()

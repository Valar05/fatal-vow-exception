#!/usr/bin/env python3
"""Build a reusable Fatal Vow 2D hand carrier from accepted k004 evidence.

The carrier is source-pixel preserving: it extracts the accepted right gripping
hand and forearm once, removes only the blue-gray donor tool, splits foreground
fingers from the rear palm/forearm, and drives both layers with the exact
camera-space Weapon.R transforms already used by the local weapon bank.

It does not generate new hands, repaint anatomy, call Blender, or complete
offscreen geometry.  The result is candidate runtime evidence until Drew rules
on the rendered watchdown.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage


WIDTH = 640
HEIGHT = 360
ATOM_ORDER = (
    ("onehandattack2.s000", "guard"),
    ("onehandattack2.s004", "anticipation"),
    ("onehandattack2.s006", "contact"),
    ("onehandattack2.s027", "recovery"),
)
CONTACT_ATOM = "onehandattack2.s006"
SEMANTIC_COLORS = {
    "rear_hand_forearm": (153, 92, 214, 255),
    "front_fingers_knuckles": (255, 153, 51, 255),
    "invalid_overlap": (255, 40, 40, 255),
}
# Source-witnessed visible exits from the accepted 640x360 FPS projection.
# These are carrier constraints, not invented offscreen completions.
FRAME_EDGE_EXITS = {
    "onehandattack2.s000": (300.0, 360.0),
    "onehandattack3.s002": (600.0, 360.0),
    "onehandattack2.s004": (118.0, 360.0),
    "onehandattack2.s006": (400.0, 360.0),
    "onehandattack2.s027": (602.0, 360.0),
}
BASE_WRIST = np.array([332.0, 225.0], dtype=np.float64)
BASE_EDGE_EXIT = np.array([400.0, 360.0], dtype=np.float64)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def polygon_mask(points: list[tuple[int, int]]) -> np.ndarray:
    image = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(image).polygon(points, fill=255)
    return np.asarray(image, dtype=np.uint8) > 0


def largest_seeded_components(mask: np.ndarray, seeds: list[tuple[int, int]]) -> np.ndarray:
    labels, _ = ndimage.label(mask)
    keep: set[int] = set()
    for x, y in seeds:
        label = int(labels[y, x])
        if label:
            keep.add(label)
    if not keep:
        raise ValueError("Accepted carrier extraction found no seeded foreground")
    return np.isin(labels, list(keep))


def extract_accepted_carrier(source: Image.Image):
    source = source.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    rgb = np.asarray(source, dtype=np.float64)
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue

    # A fixed crop around the accepted right arm prevents the left supporting
    # hand and donor tool from entering this one-hand carrier.
    arm_region = polygon_mask(
        [(252, 143), (326, 145), (363, 188), (374, 242),
         (469, 359), (309, 359), (307, 284), (279, 228), (251, 216)]
    )
    # The accepted proof uses a blue-gray tool.  Removing these pixels leaves
    # the exact hole the independent weapon layer is meant to occupy.
    donor_tool = (blue - red > 13) & (blue - green > 5) & (blue > 55)
    warm_surface = (red - blue > 1.5) & (luminance > 18)
    bright_neutral_surface = (luminance > 48) & (red >= blue - 4)
    raw = arm_region & ~donor_tool & (warm_surface | bright_neutral_surface)
    raw = ndimage.binary_closing(raw, iterations=2)
    raw = ndimage.binary_opening(raw, iterations=1)
    raw = largest_seeded_components(raw, [(333, 263), (348, 319), (274, 192), (304, 208)])
    raw = ndimage.binary_fill_holes(raw)
    # Topology repair must not resurrect the removed donor tool inside the
    # grip.  The hot-swappable weapon owns those pixels at runtime.
    raw &= ~donor_tool

    alpha = Image.fromarray((raw.astype(np.uint8) * 255), "L").filter(
        ImageFilter.GaussianBlur(0.7)
    )
    accepted_rgba = source.convert("RGBA")
    accepted_rgba.putalpha(alpha)

    # Fingers wrapping screen-left of the shaft are the foreground pass.  The
    # split is deliberately stored as a vertex/mask contract instead of baked
    # into four unrelated painted frames.
    front_region = polygon_mask(
        [(252, 151), (309, 151), (313, 176), (307, 221),
         (286, 228), (253, 216)]
    )
    front_alpha = np.asarray(alpha, dtype=np.uint8)
    front_alpha = np.where(front_region, front_alpha, 0).astype(np.uint8)
    rear_alpha = np.asarray(alpha, dtype=np.int16) - front_alpha.astype(np.int16)
    rear_alpha = np.clip(rear_alpha, 0, 255).astype(np.uint8)

    rear = source.convert("RGBA")
    rear.putalpha(Image.fromarray(rear_alpha, "L"))
    front = source.convert("RGBA")
    front.putalpha(Image.fromarray(front_alpha, "L"))

    # The reusable carrier has two deformation segments.  Hand/cuff follows
    # the weapon socket; forearm follows wrist-to-frame-edge registration.
    # Their deliberate cuff overlap prevents a crack during stepped motion.
    hand_region = polygon_mask(
        [(244, 136), (343, 136), (376, 185), (379, 248),
         (343, 269), (295, 245), (252, 216)]
    )
    forearm_region = polygon_mask(
        [(310, 198), (351, 202), (371, 245), (413, 315),
         (459, 359), (332, 359), (325, 310), (317, 260)]
    )
    hand_rear_alpha = np.where(hand_region, rear_alpha, 0).astype(np.uint8)
    # Armor is nearly as dark as the background, but remains warmer.  Use the
    # tight polygon only as jurisdiction, then recover the actual warm-edged
    # silhouette and close its internal texture gaps.  This avoids carrying a
    # black background wedge as if it were sleeve cloth.
    forearm_binary = (
        forearm_region
        & ~donor_tool
        & (red - blue > -0.5)
        & (luminance > 14)
    )
    forearm_binary = ndimage.binary_closing(forearm_binary, iterations=3)
    forearm_binary = ndimage.binary_fill_holes(forearm_binary)
    forearm_binary &= ~donor_tool
    forearm_binary = largest_seeded_components(forearm_binary, [(340, 300), (350, 340)])
    forearm_alpha = np.asarray(
        Image.fromarray((forearm_binary.astype(np.uint8) * 255), "L").filter(
            ImageFilter.GaussianBlur(0.7)
        ),
        dtype=np.uint8,
    )
    hand_rear = source.convert("RGBA")
    hand_rear.putalpha(Image.fromarray(hand_rear_alpha, "L"))
    forearm = source.convert("RGBA")
    forearm.putalpha(Image.fromarray(forearm_alpha, "L"))
    return source, hand_rear, forearm, front, donor_tool, {
        "arm_polygon_px": [[x, y] for x, y in [(252, 143), (326, 145), (363, 188), (374, 242), (469, 359), (309, 359), (307, 284), (279, 228), (251, 216)]],
        "front_finger_polygon_px": [[x, y] for x, y in [(252, 151), (309, 151), (313, 176), (307, 221), (286, 228), (253, 216)]],
        "rear_pixels": int(np.count_nonzero(rear_alpha)),
        "hand_rear_pixels": int(np.count_nonzero(hand_rear_alpha)),
        "forearm_pixels": int(np.count_nonzero(forearm_alpha)),
        "front_pixels": int(np.count_nonzero(front_alpha)),
        "donor_tool_pixels_excluded": int(np.count_nonzero(donor_tool & arm_region)),
    }


def atom_rows(catalog: dict, atom_order) -> dict[str, dict]:
    columns = catalog["pose_atom_columns"]
    rows = {row[0]: dict(zip(columns, row)) for row in catalog["pose_atoms"]}
    return {atom: rows[atom] for atom, _ in atom_order}


def socket_basis(render_module, row: dict):
    record = row["weapon_registration"]["Weapon.R"]["model"]
    matrix = render_module.trs_matrix(record)
    points = np.array([[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.20, 1.0]])
    world = (matrix @ points.T).T[:, :3]
    projected = render_module.project(world)
    origin = projected[0, :2]
    axis = projected[1, :2] - origin
    if np.linalg.norm(axis) < 1e-6:
        raise ValueError("Projected Weapon.R +Z axis collapsed")
    return origin, axis


def similarity(source_origin, source_axis, target_origin, target_axis):
    source_complex = complex(float(source_axis[0]), float(source_axis[1]))
    target_complex = complex(float(target_axis[0]), float(target_axis[1]))
    ratio = target_complex / source_complex
    a, b = ratio.real, ratio.imag
    sx, sy = map(float, source_origin)
    tx = float(target_origin[0]) - (a * sx - b * sy)
    ty = float(target_origin[1]) - (b * sx + a * sy)
    return a, b, tx, ty


def transform_rgba(image: Image.Image, transform):
    a, b, tx, ty = transform
    determinant = a * a + b * b
    if determinant < 1e-10:
        raise ValueError("Degenerate carrier transform")
    inverse = (
        a / determinant,
        b / determinant,
        -(a * tx + b * ty) / determinant,
        -b / determinant,
        a / determinant,
        (b * tx - a * ty) / determinant,
    )
    return image.transform(
        (WIDTH, HEIGHT),
        Image.Transform.AFFINE,
        inverse,
        resample=Image.Resampling.BICUBIC,
    )


def transform_rgba_affine(image: Image.Image, matrix: np.ndarray, translation: np.ndarray):
    inverse_matrix = np.linalg.inv(matrix)
    inverse_translation = -inverse_matrix @ translation
    return image.transform(
        (WIDTH, HEIGHT),
        Image.Transform.AFFINE,
        (
            float(inverse_matrix[0, 0]),
            float(inverse_matrix[0, 1]),
            float(inverse_translation[0]),
            float(inverse_matrix[1, 0]),
            float(inverse_matrix[1, 1]),
            float(inverse_translation[1]),
        ),
        resample=Image.Resampling.BICUBIC,
    )


def forearm_affine(target_wrist: np.ndarray, target_exit: np.ndarray, hand_scale: float):
    source_long = BASE_EDGE_EXIT - BASE_WRIST
    target_long = target_exit - target_wrist
    if np.linalg.norm(target_long) < 1e-6:
        raise ValueError("Forearm frame-edge exit collapsed onto wrist")
    source_cross = np.array([-source_long[1], source_long[0]])
    target_cross = np.array([-target_long[1], target_long[0]])
    target_cross *= np.linalg.norm(source_cross) * hand_scale / np.linalg.norm(target_cross)
    source_basis = np.stack([source_long, source_cross], axis=1)
    target_basis = np.stack([target_long, target_cross], axis=1)
    matrix = target_basis @ np.linalg.inv(source_basis)
    translation = target_wrist - matrix @ BASE_WRIST
    return matrix, translation


def apply_similarity_point(point: np.ndarray, transform) -> np.ndarray:
    a, b, tx, ty = transform
    x, y = map(float, point)
    return np.array([a * x - b * y + tx, b * x + a * y + ty])


def semantic_layer(layer: Image.Image, color: tuple[int, int, int, int]):
    result = Image.new("RGBA", layer.size, color)
    result.putalpha(layer.getchannel("A"))
    return result


def dark_review(frame: Image.Image):
    result = Image.new("RGBA", frame.size, (10, 13, 18, 255))
    result.alpha_composite(frame)
    return result.convert("RGB")


def labeled_sheet(frames: list[Image.Image], labels: list[str]):
    sheet = Image.new("RGB", (WIDTH * 2, HEIGHT * 2), (10, 13, 18))
    font = ImageFont.load_default()
    for index, (frame, label) in enumerate(zip(frames, labels)):
        review = dark_review(frame)
        draw = ImageDraw.Draw(review)
        draw.rectangle((0, 0, WIDTH, 24), fill=(3, 5, 8))
        draw.text((8, 7), label, fill=(245, 245, 245), font=font)
        sheet.paste(review, ((index % 2) * WIDTH, (index // 2) * HEIGHT))
    return sheet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-proof", type=Path, required=True)
    parser.add_argument("--hero-plate", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--sentence", type=Path)
    parser.add_argument("--weapon-bank", type=Path, required=True)
    parser.add_argument("--semantic-weapon-bank", type=Path)
    parser.add_argument("--weapon-renderer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    layers_dir = args.output / "layers"
    frames_dir = args.output / "frames"
    layers_dir.mkdir(exist_ok=True)
    frames_dir.mkdir(exist_ok=True)

    if sha256(args.accepted_proof) != "e5b472dbe5dc97c8e2a9a61c02f43cc8c89aaa3cc4254bcd6fc67f0c74990857":
        raise ValueError("Accepted k004 proof identity changed")
    if sha256(args.hero_plate) != "bf6a3107e26d6bba55ebcf933bb58517a17d9ba163b3c0c7d9deb93cbd68e18c":
        raise ValueError("Hero hand authority changed")

    render_module = load_module(args.weapon_renderer, "fatal_vow_weapon_renderer")
    catalog = json.loads(args.catalog.read_text())
    if args.sentence:
        sentence = json.loads(args.sentence.read_text())
        atom_order = tuple(
            (recipe["atom"], role) for role, recipe in sentence["recipes"].items()
        )
        contact_atoms = [
            recipe["atom"] for role, recipe in sentence["recipes"].items()
            if role == "contact"
        ]
        if len(contact_atoms) != 1:
            raise ValueError("Sentence must contain exactly one contact recipe")
        contact_atom = contact_atoms[0]
    else:
        atom_order = ATOM_ORDER
        contact_atom = CONTACT_ATOM
    rows = atom_rows(catalog, atom_order)
    accepted_source = Image.open(args.accepted_proof)
    resized, base_hand_rear, base_forearm, base_front, _, extraction = extract_accepted_carrier(accepted_source)
    base_rear = Image.alpha_composite(base_forearm, base_hand_rear)
    base_rear.save(layers_dir / "carrier-base-rear-hand-forearm.png")
    base_hand_rear.save(layers_dir / "carrier-base-rear-hand.png")
    base_forearm.save(layers_dir / "carrier-base-forearm.png")
    base_front.save(layers_dir / "carrier-base-front-fingers-knuckles.png")
    base_debug = Image.alpha_composite(
        semantic_layer(base_rear, SEMANTIC_COLORS["rear_hand_forearm"]),
        semantic_layer(base_front, SEMANTIC_COLORS["front_fingers_knuckles"]),
    )
    base_debug.save(layers_dir / "carrier-base-vertex-color.png")

    contact_origin, contact_axis = socket_basis(render_module, rows[contact_atom])
    composites: list[Image.Image] = []
    diagnostics: list[Image.Image] = []
    labels: list[str] = []
    frame_records = []
    for index, (atom, role) in enumerate(atom_order):
        target_origin, target_axis = socket_basis(render_module, rows[atom])
        carrier_transform = similarity(
            contact_origin, contact_axis, target_origin, target_axis
        )
        hand_rear = transform_rgba(base_hand_rear, carrier_transform)
        target_wrist = apply_similarity_point(BASE_WRIST, carrier_transform)
        target_exit = np.asarray(FRAME_EDGE_EXITS[atom], dtype=np.float64)
        forearm_matrix, forearm_translation = forearm_affine(
            target_wrist,
            target_exit,
            math.hypot(carrier_transform[0], carrier_transform[1]),
        )
        forearm = transform_rgba_affine(
            base_forearm, forearm_matrix, forearm_translation
        )
        rear = Image.alpha_composite(forearm, hand_rear)
        front = transform_rgba(base_front, carrier_transform)
        rear_path = layers_dir / f"{index:02d}-{role}-rear-hand-forearm.png"
        front_path = layers_dir / f"{index:02d}-{role}-front-fingers-knuckles.png"
        rear.save(rear_path)
        front.save(front_path)

        weapon_path = args.weapon_bank / "frames" / f"{index:02d}-{role}.png"
        weapon = Image.open(weapon_path).convert("RGBA")
        composed = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        composed.alpha_composite(rear)
        composed.alpha_composite(weapon)
        composed.alpha_composite(front)
        composed_path = frames_dir / f"{index:02d}-{role}-composed.png"
        composed.save(composed_path)

        semantic_weapon_path = (
            args.semantic_weapon_bank / "frames" / f"{index:02d}-{role}.png"
            if args.semantic_weapon_bank
            else weapon_path
        )
        semantic_weapon = Image.open(semantic_weapon_path).convert("RGBA")
        diagnostic = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        diagnostic.alpha_composite(
            semantic_layer(rear, SEMANTIC_COLORS["rear_hand_forearm"])
        )
        diagnostic.alpha_composite(semantic_weapon)
        diagnostic.alpha_composite(
            semantic_layer(front, SEMANTIC_COLORS["front_fingers_knuckles"])
        )
        diagnostic_path = frames_dir / f"{index:02d}-{role}-vertex-color.png"
        diagnostic.save(diagnostic_path)

        if not rear.getbbox() or not front.getbbox() or not composed.getbbox():
            raise ValueError(f"{atom} produced a blank required layer")
        labels.append(f"{atom} · {role}")
        composites.append(composed)
        diagnostics.append(diagnostic)
        frame_records.append(
            {
                "atom": atom,
                "role": role,
                "time_seconds": rows[atom]["time_seconds"],
                "similarity": {
                    "a": carrier_transform[0],
                    "b": carrier_transform[1],
                    "tx": carrier_transform[2],
                    "ty": carrier_transform[3],
                    "scale": math.hypot(carrier_transform[0], carrier_transform[1]),
                    "rotation_degrees": math.degrees(math.atan2(carrier_transform[1], carrier_transform[0])),
                },
                "forearm_registration": {
                    "wrist_px": target_wrist.tolist(),
                    "frame_edge_exit_px": list(FRAME_EDGE_EXITS[atom]),
                    "matrix": forearm_matrix.tolist(),
                    "translation": forearm_translation.tolist(),
                },
                "rear_hand_forearm": str(rear_path.relative_to(args.output)),
                "rear_hand_forearm_sha256": sha256(rear_path),
                "weapon": str(weapon_path.relative_to(args.weapon_bank.parent)),
                "weapon_sha256": sha256(weapon_path),
                "semantic_weapon": str(semantic_weapon_path),
                "semantic_weapon_sha256": sha256(semantic_weapon_path),
                "front_fingers_knuckles": str(front_path.relative_to(args.output)),
                "front_fingers_knuckles_sha256": sha256(front_path),
                "composed": str(composed_path.relative_to(args.output)),
                "composed_sha256": sha256(composed_path),
                "vertex_color": str(diagnostic_path.relative_to(args.output)),
                "vertex_color_sha256": sha256(diagnostic_path),
            }
        )

    sheet_path = args.output / "onehandattack2-hand-carrier-contact-sheet.png"
    labeled_sheet(composites, labels).save(sheet_path)
    debug_sheet_path = args.output / "onehandattack2-hand-carrier-vertex-color-contact-sheet.png"
    labeled_sheet(diagnostics, labels).save(debug_sheet_path)
    timeline = [0, 1, 2, 2, 3, 3, 3, 3]
    gif_frames = [dark_review(composites[i]) for i in timeline]
    gif_path = args.output / "onehandattack2-hand-carrier-watchdown.gif"
    gif_frames[0].save(
        gif_path, save_all=True, append_images=gif_frames[1:],
        duration=[100] * len(gif_frames), loop=0, disposal=2
    )
    debug_gif_frames = [dark_review(diagnostics[i]) for i in timeline]
    debug_gif_path = args.output / "onehandattack2-hand-carrier-vertex-color-watchdown.gif"
    debug_gif_frames[0].save(
        debug_gif_path, save_all=True, append_images=debug_gif_frames[1:],
        duration=[100] * len(debug_gif_frames), loop=0, disposal=2
    )

    manifest = {
        "schema": "fatal-vow.vertex-hand-carrier/v1",
        "status": "candidate_visual_evidence",
        "authorized_lane": "local_only",
        "source_policy": "accepted k004 pixels transformed; no generated or repainted hand pixels",
        "accepted_sources": {
            "k004_proof": {"filename": args.accepted_proof.name, "sha256": sha256(args.accepted_proof)},
            "hero_plate": {"filename": args.hero_plate.name, "sha256": sha256(args.hero_plate)},
        },
        "carrier": {
            "reference_atom": contact_atom,
            "grip_class": "one_hand_long_handle",
            "deformation_segments": [
                "hand_cuff_follows_weapon_socket",
                "forearm_follows_wrist_to_frame_edge_exit",
            ],
            "vertex_colors": {key: "#" + "".join(f"{v:02X}" for v in value[:3]) for key, value in SEMANTIC_COLORS.items()},
            "extraction": extraction,
            "layers": ["rear_hand_forearm", "weapon", "front_fingers_knuckles"],
        },
        "frames": frame_records,
        "score": {"timeline_frame_indices": timeline, "durations_ms": [100] * len(timeline)},
        "outputs": {
            "contact_sheet": {"path": sheet_path.name, "sha256": sha256(sheet_path)},
            "vertex_color_contact_sheet": {"path": debug_sheet_path.name, "sha256": sha256(debug_sheet_path)},
            "watchdown": {"path": gif_path.name, "sha256": sha256(gif_path)},
            "vertex_color_watchdown": {"path": debug_gif_path.name, "sha256": sha256(debug_gif_path)},
        },
        "claim_boundary": "Layer completeness and deterministic registration may pass. Pose quality, final grip readability, and acceptance remain human visual judgments.",
    }
    manifest_path = args.output / "onehandattack2-hand-carrier.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "frames": len(frame_records), "manifest": str(manifest_path)}))


if __name__ == "__main__":
    main()

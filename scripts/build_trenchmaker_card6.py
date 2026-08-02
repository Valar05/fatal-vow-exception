#!/usr/bin/env python3
"""Build the first Vow Motion Lab visual specimen.

This is a pose-only Card 6 / Cards 1, 2, 7 proof.  It preserves the accepted
hero-hand pixels, keeps rear hand, shovel, foreground fingers, and supporting
hand independently registered, and renders slide -> catch -> brake grip
ownership without effects, blood, camera violence, or terrain fragments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from scipy import ndimage


W, H = 640, 360
BG = (8, 11, 13, 255)
POSES = (
    ("LOAD", "00-guard", (418, 165), (600, 360), (370, 82), (78, 360), "rear hand owns; support approaches"),
    ("SLIDE", "01-anticipation", (402, 208), (110, 360), (250, 90), (560, 360), "support travels down the shaft"),
    ("CATCH", "01-anticipation", (402, 208), (110, 360), (285, 132), (575, 360), "support closes before the drive"),
    ("DRIVE", "02-contact", (305, 201), (430, 360), (304, 82), (92, 360), "both hands accelerate one line"),
    ("BRAKE", "02-contact", (305, 201), (430, 360), (304, 132), (72, 360), "support absorbs rebound at contact"),
    ("EXTRACT", "03-recovery", (555, 260), (430, 360), (574, 126), (176, 360), "rear hand pulls; support preserves path"),
)
SOURCE_HAND = np.array((196.0, 185.0))
SOURCE_EXIT = np.array((190.0, 810.0))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def extract_support_layers(sheet: Image.Image) -> tuple[Image.Image, Image.Image, dict]:
    """Extract the accepted rightmost grip and split its foreground fingers."""
    crop_box = (1200, 42, 1595, 900)
    crop = sheet.convert("RGB").crop(crop_box)
    rgb = np.asarray(crop, dtype=np.float32)
    border = np.concatenate((rgb[:24].reshape(-1, 3), rgb[-24:].reshape(-1, 3),
                             rgb[:, :18].reshape(-1, 3), rgb[:, -18:].reshape(-1, 3)))
    background = np.median(border, axis=0)
    luminance = rgb.mean(axis=2)
    # The sheet is painted on textured parchment, so global color distance is
    # not a safe matte.  Bind extraction to the witnessed limb silhouette and
    # use skin red-dominance / dark costume separation inside that boundary.
    witness = Image.new("L", crop.size, 0)
    ImageDraw.Draw(witness).polygon(
        [(194, 54), (258, 70), (313, 150), (298, 282), (292, 430),
         (321, 660), (332, 797), (165, 852), (66, 735), (76, 455),
         (88, 286), (58, 185), (78, 104), (142, 72)], fill=255
    )
    red_dominance = (rgb[..., 0] - rgb[..., 1] > 16.0) & (rgb[..., 0] - rgb[..., 2] > 24.0)
    material = (luminance < 132.0) | red_dominance
    body = material & (np.asarray(witness) > 0)
    body = ndimage.binary_closing(body, iterations=2)
    body = ndimage.binary_opening(body, iterations=1)
    alpha = Image.fromarray((body * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
    rgba = crop.convert("RGBA")
    rgba.putalpha(alpha)

    front_mask = Image.new("L", crop.size, 0)
    ImageDraw.Draw(front_mask).polygon(
        [(74, 80), (251, 62), (286, 154), (267, 271), (102, 286), (59, 187)], fill=255
    )
    front_alpha = Image.fromarray(
        np.minimum(np.asarray(alpha), np.asarray(front_mask)).astype(np.uint8)
    )
    rear_alpha = Image.fromarray(
        np.where(np.asarray(front_mask) > 0, 0, np.asarray(alpha)).astype(np.uint8)
    )
    rear = rgba.copy(); rear.putalpha(rear_alpha)
    front = rgba.copy(); front.putalpha(front_alpha)
    return rear, front, {
        "source_crop": list(crop_box),
        "source_hand": SOURCE_HAND.tolist(),
        "source_exit": SOURCE_EXIT.tolist(),
        "background_rgb_median": [round(float(x), 2) for x in background],
        "support_pixels": int(body.sum()),
    }


def register(layer: Image.Image, target_hand: tuple[int, int], target_exit: tuple[int, int]) -> Image.Image:
    source_axis = SOURCE_HAND - SOURCE_EXIT
    target_axis = np.array(target_hand, dtype=float) - np.array(target_exit, dtype=float)
    source_len = np.linalg.norm(source_axis)
    target_len = np.linalg.norm(target_axis)
    su = source_axis / source_len
    sv = np.array((-su[1], su[0]))
    tu = target_axis / target_len
    tv = np.array((-tu[1], tu[0]))
    scale_along = target_len / source_len
    scale_across = scale_along * 0.78
    a = np.column_stack((tu * scale_along, tv * scale_across)) @ np.vstack((su, sv))
    t = np.array(target_exit, dtype=float) - a @ SOURCE_EXIT
    inv = np.linalg.inv(a)
    inv_t = -inv @ t
    coeffs = (inv[0, 0], inv[0, 1], inv_t[0], inv[1, 0], inv[1, 1], inv_t[1])
    return layer.transform((W, H), Image.Transform.AFFINE, coeffs,
                           resample=Image.Resampling.BICUBIC)


def tint(layer: Image.Image, color: tuple[int, int, int], opacity: int = 210) -> Image.Image:
    alpha = layer.getchannel("A").point(lambda x: x * opacity // 255)
    out = Image.new("RGBA", layer.size, color + (0,))
    out.putalpha(alpha)
    return out


def backdrop(label: str) -> Image.Image:
    image = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(image)
    for y in range(H):
        v = int(8 + 13 * y / H)
        draw.line((0, y, W, y), fill=(v, v + 3, v + 4, 255))
    draw.rectangle((0, 276, W, H), fill=(22, 20, 18, 255))
    for x in range(0, W, 37):
        draw.line((x, 282 + (x % 17), x + 45, 360), fill=(34, 29, 24, 255), width=2)
    draw.text((14, 12), label, font=font(20), fill=(238, 229, 211, 255))
    return image


def load_weapon(root: Path, stem: str) -> Image.Image:
    path = root / "evidence/onehandattack2-grammar-bank-material/frames" / f"{stem}.png"
    return Image.open(path).convert("RGBA")


def make_frames(root: Path, support_rear: Image.Image, support_front: Image.Image):
    material, diagnostic, silhouette = [], [], []
    head_path = [(421, 187), (258, 35), (258, 35), (303, 276), (303, 276), (622, 35)]
    for index, (label, stem, rear_hand, rear_exit, target_hand, target_exit, sentence) in enumerate(POSES):
        weapon = load_weapon(root, stem)
        rear = register(support_rear, rear_hand, rear_exit)
        front = register(support_front, rear_hand, rear_exit)
        s_rear = register(support_rear, target_hand, target_exit)
        s_front = register(support_front, target_hand, target_exit)

        full = backdrop(f"TRENCHMAKER / {label}")
        for layer in (rear, s_rear, weapon, s_front, front):
            full.alpha_composite(layer)
        d = ImageDraw.Draw(full)
        d.text((14, 332), sentence, font=font(14), fill=(221, 211, 193, 255))
        material.append(full)

        diag = backdrop(f"GRIP OWNERSHIP / {label}")
        for layer in (tint(rear, (153, 92, 214)), tint(s_rear, (244, 164, 45)),
                      tint(weapon, (66, 210, 196), 235), tint(s_front, (255, 185, 55)),
                      tint(front, (255, 75, 174))):
            diag.alpha_composite(layer)
        dd = ImageDraw.Draw(diag)
        dd.line((0, 276, W, 276), fill=(247, 79, 79, 255), width=3)
        if index > 0:
            dd.line(head_path[:index + 1], fill=(89, 216, 255, 190), width=3)
        dd.ellipse((target_hand[0]-8, target_hand[1]-8, target_hand[0]+8, target_hand[1]+8),
                   outline=(255, 222, 91, 255), width=3)
        dd.line((target_exit, target_hand), fill=(255, 222, 91, 180), width=2)
        dd.text((14, 306), "purple rear | gold support | cyan shovel | pink foreground | red collision",
                font=font(12), fill=(236, 232, 220, 255))
        diagnostic.append(diag)

        combined_alpha = np.maximum.reduce([
            np.asarray(x.getchannel("A")) for x in (rear, s_rear, weapon, s_front, front)
        ])
        sil = backdrop(f"SILHOUETTE / {label}")
        white = Image.new("RGBA", (W, H), (241, 237, 224, 0))
        white.putalpha(Image.fromarray(combined_alpha.astype(np.uint8)))
        sil.alpha_composite(white)
        ImageDraw.Draw(sil).line((0, 276, W, 276), fill=(247, 79, 79, 255), width=3)
        silhouette.append(sil)
    return material, diagnostic, silhouette


def make_sheet(frames: list[Image.Image], title: str, path: Path):
    thumb_w, thumb_h = 512, 288
    canvas = Image.new("RGB", (thumb_w * 3, thumb_h * 2 + 72), (7, 9, 11))
    draw = ImageDraw.Draw(canvas)
    draw.text((18, 16), title, font=font(30), fill=(238, 229, 211))
    for i, frame in enumerate(frames):
        frame = frame.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS).convert("RGB")
        canvas.paste(frame, ((i % 3) * thumb_w, 72 + (i // 3) * thumb_h))
    canvas.save(path, optimize=True)


def save_gif(material: list[Image.Image], diagnostic: list[Image.Image], path: Path, slow: bool):
    joined = []
    for left, right in zip(material, diagnostic):
        frame = Image.new("RGB", (W * 2, H), (0, 0, 0))
        frame.paste(left.convert("RGB"), (0, 0))
        frame.paste(right.convert("RGB"), (W, 0))
        joined.append(frame)
    order = [0, 1, 2, 3, 3, 4, 5, 5]
    duration = 320 if slow else 115
    exposed = [joined[i] for i in order]
    exposed[0].save(path, save_all=True, append_images=exposed[1:], duration=duration,
                    loop=0, disposal=2, optimize=False)


def save_review_gif(material: list[Image.Image], diagnostic: list[Image.Image], path: Path):
    frames = []
    for left, right in zip(material, diagnostic):
        frame = Image.new("RGB", (W * 2, H), (0, 0, 0))
        frame.paste(left.convert("RGB"), (0, 0))
        frame.paste(right.convert("RGB"), (W, 0))
        frame = frame.resize((960, 270), Image.Resampling.LANCZOS)
        frames.append(frame.quantize(colors=48, method=Image.Quantize.MEDIANCUT))
    order = [0, 1, 2, 3, 3, 4, 5, 5]
    exposed = [frames[i] for i in order]
    exposed[0].save(path, save_all=True, append_images=exposed[1:], duration=130,
                    loop=0, disposal=2, optimize=True)


def save_review_board(sheet_paths: list[Path], path: Path) -> None:
    panels = [Image.open(p).convert("RGB").resize((1152, 486), Image.Resampling.LANCZOS)
              for p in sheet_paths]
    board = Image.new("RGB", (1152, 1458), (7, 9, 11))
    for i, panel in enumerate(panels):
        board.paste(panel, (0, i * 486))
    board.quantize(colors=96, method=Image.Quantize.MEDIANCUT,
                   dither=Image.Dither.NONE).save(path, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hero-plate", required=True, type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path("evidence/trenchmaker-card6"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / args.output
    output.mkdir(parents=True, exist_ok=True)
    support_rear, support_front, extraction = extract_support_layers(Image.open(args.hero_plate))
    material, diagnostic, silhouette = make_frames(root, support_rear, support_front)

    paths = {
        "watchdown": output / "trenchmaker-card6-watchdown.gif",
        "slow_watchdown": output / "trenchmaker-card6-slow-watchdown.gif",
        "contact_sheet": output / "trenchmaker-card6-contact-sheet.png",
        "silhouette_sheet": output / "trenchmaker-card6-silhouette-sheet.png",
        "registration_sheet": output / "trenchmaker-card6-grip-registration-sheet.png",
        "review_gif": output / "trenchmaker-card6-review.gif",
        "review_board": output / "trenchmaker-card6-review-board.png",
    }
    save_gif(material, diagnostic, paths["watchdown"], False)
    save_gif(material, diagnostic, paths["slow_watchdown"], True)
    make_sheet(material, "VOW MOTION LAB — TRENCHMAKER POSE SENTENCE", paths["contact_sheet"])
    make_sheet(silhouette, "TRENCHMAKER — SILHOUETTE / COLLISION PLANE", paths["silhouette_sheet"])
    make_sheet(diagnostic, "CARD 6 — TWO-HAND SLIDE / CATCH / BRAKE", paths["registration_sheet"])
    save_review_gif(material, diagnostic, paths["review_gif"])
    save_review_board([paths["contact_sheet"], paths["registration_sheet"],
                       paths["silhouette_sheet"]], paths["review_board"])

    manifest = {
        "schema": "fatal-vow.motion-lab-specimen/v1",
        "id": "trenchmaker-card6-pose-only-v0",
        "status": "candidate_visual_evidence",
        "cards": [1, 2, 6, 7],
        "pose_sentence": [pose[0].lower() for pose in POSES],
        "constraints": {
            "pose_only": True,
            "effects": False,
            "supporting_hand": "accepted hero-hand pixels; transformed; separately registered",
            "layers": ["rear_hand_forearm", "support_rear", "shovel", "support_front", "foreground_fingers"],
            "collision_plane_y": 276,
            "source_product": "Fatal Vow Exception",
            "deprecated_reference_only": "Infinite Brutality",
        },
        "hero_hand_source": {
            "filename": args.hero_plate.name,
            "sha256": sha256(args.hero_plate),
            "extraction": extraction,
        },
        "outputs": {name: {"path": str(paths[name].relative_to(root)), "sha256": sha256(paths[name])}
                    for name in ("review_gif", "review_board")},
        "generated_derivatives": [
            str(paths[name].relative_to(root)) for name in
            ("watchdown", "slow_watchdown", "contact_sheet", "silhouette_sheet", "registration_sheet")
        ],
        "claim_boundary": "First reviewable Stage 1 specimen. Technical generation does not grant visual acceptance or runtime promotion.",
    }
    manifest_path = output / "trenchmaker-card6.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

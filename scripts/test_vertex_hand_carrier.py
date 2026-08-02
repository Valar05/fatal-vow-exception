#!/usr/bin/env python3
"""Validate the published vertex-hand-carrier evidence contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
HAND_DIR = ROOT / "evidence/onehandattack2-hand-carrier"
SEMANTIC_DIR = ROOT / "evidence/onehandattack2-grammar-bank-semantic"
MATERIAL_DIR = ROOT / "evidence/onehandattack2-grammar-bank-material"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    compiled = load(ROOT / "data/grammar_sentences/onehandattack2_minimal_v0.compiled.json")
    assert compiled["motion_compile_status"] == "pass"
    assert compiled["visual_compile_status"] == "ready_for_render"
    assert compiled["missing_layers"] == []
    assert compiled["layer_artifact_failures"] == []
    assert len(compiled["timeline"]) == 8
    assert len(compiled["resolved_layer_artifacts"]) == 4
    assert sum(len(value) for value in compiled["resolved_layer_artifacts"].values()) == 12

    hand = load(HAND_DIR / "onehandattack2-hand-carrier.manifest.json")
    semantic = load(SEMANTIC_DIR / "onehandattack2-local-weapon-bank.manifest.json")
    material = load(MATERIAL_DIR / "onehandattack2-local-weapon-bank.manifest.json")
    expected_atoms = [
        "onehandattack3.s002",
        "onehandattack2.s004",
        "onehandattack2.s006",
        "onehandattack2.s027",
    ]
    assert [frame["atom"] for frame in hand["frames"]] == expected_atoms
    assert semantic["sentence"]["atom_order"] == expected_atoms
    assert material["sentence"]["atom_order"] == expected_atoms
    assert semantic["source_atlas"]["render_color_mode"] == "semantic"
    assert material["source_atlas"]["render_color_mode"] == "material-vertex"
    assert semantic["source_atlas"]["local_axes_atlas"]["z_toward_blade"] == [
        -0.6167137618421145,
        -0.7871874846277396,
        0.0,
    ]

    for frame in hand["frames"]:
        for field in (
            "rear_hand_forearm",
            "front_fingers_knuckles",
            "composed",
            "vertex_color",
        ):
            path = HAND_DIR / frame[field]
            assert path.is_file(), path
            assert digest(path) == frame[f"{field}_sha256"]
            with Image.open(path) as image:
                assert image.size == (640, 360)
                assert image.convert("RGBA").getchannel("A").getbbox()

    for name, record in hand["outputs"].items():
        path = HAND_DIR / record["path"]
        assert digest(path) == record["sha256"], name

    for gif_name in ("watchdown", "vertex_color_watchdown"):
        path = HAND_DIR / hand["outputs"][gif_name]["path"]
        with Image.open(path) as gif:
            durations = []
            for frame in range(gif.n_frames):
                gif.seek(frame)
                durations.append(gif.info["duration"])
        # Pillow coalesces identical hold/recovery exposures.  The encoded
        # centisecond schedule must still preserve the authored 0.8 seconds.
        assert durations == [100, 100, 200, 400]
        assert sum(durations) == 800

    semantic_hashes = [digest(SEMANTIC_DIR / frame["output"]) for frame in semantic["frames"]]
    material_hashes = [digest(MATERIAL_DIR / frame["output"]) for frame in material["frames"]]
    assert all(first != second for first, second in zip(semantic_hashes, material_hashes))
    print(json.dumps({"status": "PASS", "layers": 12, "timeline_frames": 8, "atoms": expected_atoms}))


if __name__ == "__main__":
    main()

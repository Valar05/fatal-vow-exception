#!/usr/bin/env python3
"""Artifact contract for the first Vow Motion Lab specimen."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evidence/trenchmaker-card6/trenchmaker-card6.manifest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["status"] == "candidate_visual_evidence"
    assert data["cards"] == [1, 2, 6, 7]
    assert data["pose_sentence"] == ["load", "slide", "catch", "drive", "brake", "extract"]
    assert data["constraints"]["pose_only"] is True
    assert data["constraints"]["effects"] is False
    assert data["hero_hand_source"]["sha256"] == "bf6a3107e26d6bba55ebcf933bb58517a17d9ba163b3c0c7d9deb93cbd68e18c"
    assert set(data["outputs"]) == {"review_gif", "review_board"}
    for artifact in data["outputs"].values():
        path = ROOT / artifact["path"]
        assert path.is_file(), path
        assert digest(path) == artifact["sha256"]
    gif = Image.open(ROOT / data["outputs"]["review_gif"]["path"])
    assert gif.size == (960, 270)
    assert gif.n_frames >= 6
    board = Image.open(ROOT / data["outputs"]["review_board"]["path"])
    assert board.size == (1152, 1458)
    print("trenchmaker-card6: pass")


if __name__ == "__main__":
    main()

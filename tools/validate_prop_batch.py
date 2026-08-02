#!/usr/bin/env python3
"""Fail closed when the processed Fatal Vow prop batch drifts."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from PIL import Image

from process_prop_batch import PROPS, accessor, load_glb, sha256


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--write-report", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures: list[str] = []
    checks: list[str] = []

    def require(condition: bool, message: str) -> None:
        (checks if condition else failures).append(message)

    require(manifest.get("schema") == "fatal-vow.prop-batch.v1", "manifest schema")
    require(sha256(args.source) == manifest["source"]["sha256"], "source SHA-256")
    require(args.source.stat().st_size == manifest["source"]["bytes"], "source byte count")
    source_document, source_binary = load_glb(args.source)
    source_primitive = source_document["meshes"][0]["primitives"][0]
    source_triangles = len(accessor(source_document, source_binary, source_primitive["indices"])) // 3
    require(source_triangles == manifest["source"]["triangle_count"], "source triangle count")
    require([item["name"] for item in manifest["props"]] == PROPS, "twelve canonical prop names/order")

    total_triangles = 0
    total_bytes = 0
    for item in manifest["props"]:
        path = args.manifest.parent / item["path"]
        require(path.exists(), f"{item['name']}: file exists")
        if not path.exists():
            continue
        require(sha256(path) == item["sha256"], f"{item['name']}: SHA-256")
        require(path.stat().st_size == item["bytes"], f"{item['name']}: byte count")
        document, binary = load_glb(path)
        require(len(document.get("nodes", [])) == 1, f"{item['name']}: one node")
        require(len(document.get("meshes", [])) == 1, f"{item['name']}: one mesh")
        require(not document.get("animations"), f"{item['name']}: no animations")
        require(not document.get("skins"), f"{item['name']}: no skins")
        primitive = document["meshes"][0]["primitives"][0]
        triangle_count = len(accessor(document, binary, primitive["indices"])) // 3
        require(triangle_count == item["triangle_count"], f"{item['name']}: triangle count")
        require(len(document.get("images", [])) == 4, f"{item['name']}: four embedded textures")
        for image_entry in document.get("images", []):
            view = document["bufferViews"][image_entry["bufferView"]]
            payload = binary[view.get("byteOffset", 0) : view.get("byteOffset", 0) + view["byteLength"]]
            image = Image.open(io.BytesIO(payload))
            require(tuple(image.size) == tuple(manifest["processing"]["texture_size"]), f"{item['name']}: {image_entry.get('name')} texture size")
        total_triangles += triangle_count
        total_bytes += path.stat().st_size

    require(total_triangles == manifest["processing"]["preserved_source_triangle_count"], "combined output triangle count")
    require(source_triangles - total_triangles == manifest["processing"]["removed_triangle_count"], "bounded debris removal count")
    require(manifest["processing"]["removed_triangle_count"] == 1, "exactly one reviewed debris triangle removed")
    contact = args.manifest.parent / manifest["contact_sheet"]["path"]
    require(contact.exists(), "contact sheet exists")
    if contact.exists():
        require(sha256(contact) == manifest["contact_sheet"]["sha256"], "contact sheet SHA-256")

    report = {
        "schema": "fatal-vow.prop-batch-validation.v1",
        "status": "PASS" if not failures else "FAIL",
        "source_sha256": sha256(args.source),
        "prop_count": len(manifest.get("props", [])),
        "source_triangles": source_triangles,
        "output_triangles": total_triangles,
        "removed_triangles": source_triangles - total_triangles,
        "processed_glb_bytes": total_bytes,
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

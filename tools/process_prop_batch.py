#!/usr/bin/env python3
"""Split the approved 4x3 Meshy prop sheet into twelve small, centered GLBs.

The source is intentionally preserved.  This processor assigns disconnected
triangle islands to their spatial source-sheet cell, removes only isolated
single-triangle debris, downsizes the four baked textures, and records enough
information to reproduce or audit every output.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


PROPS = [
    "scarred-d-grip-shovel",
    "spear",
    "glass-launcher",
    "glass-cartridge",
    "braided-wire",
    "ceramic-key",
    "ration-bar",
    "bone-needle-case",
    "clinic-needle",
    "compliance-mushroom",
    "flint-kit",
    "beetle-venom-vial",
]

COMPONENT_DTYPES = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}
COMPONENT_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    magic, version, declared = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or declared != len(data):
        raise ValueError(f"{path}: invalid GLB 2.0 header")
    json_len, json_type = struct.unpack_from("<I4s", data, 12)
    if json_type != b"JSON":
        raise ValueError(f"{path}: first GLB chunk is not JSON")
    document = json.loads(data[20 : 20 + json_len].decode("utf-8"))
    offset = 20 + json_len
    bin_len, bin_type = struct.unpack_from("<I4s", data, offset)
    if bin_type != b"BIN\x00":
        raise ValueError(f"{path}: second GLB chunk is not BIN")
    return document, data[offset + 8 : offset + 8 + bin_len]


def accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    item = document["accessors"][index]
    view = document["bufferViews"][item["bufferView"]]
    dtype = np.dtype(COMPONENT_DTYPES[item["componentType"]])
    width = COMPONENT_COUNTS[item["type"]]
    stride = view.get("byteStride", dtype.itemsize * width)
    offset = view.get("byteOffset", 0) + item.get("byteOffset", 0)
    if stride == dtype.itemsize * width:
        return np.frombuffer(
            binary, dtype=dtype, count=item["count"] * width, offset=offset
        ).reshape(item["count"], width).copy()
    result = np.empty((item["count"], width), dtype=dtype)
    for row in range(item["count"]):
        result[row] = np.frombuffer(
            binary, dtype=dtype, count=width, offset=offset + row * stride
        )
    return result


def connected_components(indices: np.ndarray, vertex_count: int) -> list[np.ndarray]:
    parent = np.arange(vertex_count)

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = int(parent[value])
        return value

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    for triangle in indices:
        union(int(triangle[0]), int(triangle[1]))
        union(int(triangle[0]), int(triangle[2]))
    grouped: dict[int, list[int]] = defaultdict(list)
    for triangle_index, triangle in enumerate(indices):
        grouped[find(int(triangle[0]))].append(triangle_index)
    return [np.asarray(rows, dtype=np.int64) for rows in grouped.values()]


def pad4(data: bytes, fill: bytes = b"\x00") -> bytes:
    return data + fill * ((-len(data)) % 4)


def encode_jpeg(source: bytes, size: int, quality: int) -> bytes:
    image = Image.open(io.BytesIO(source)).convert("RGB")
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, "JPEG", quality=quality, optimize=True, progressive=True)
    return output.getvalue()


def build_glb(
    name: str,
    attributes: dict[str, np.ndarray],
    indices: np.ndarray,
    images: list[tuple[str, bytes]],
    source_document: dict,
    destination: Path,
) -> None:
    chunks: list[bytes] = []
    views: list[dict] = []

    def add_view(payload: bytes, target: int | None = None) -> int:
        offset = sum(len(chunk) for chunk in chunks)
        padded = pad4(payload)
        chunks.append(padded)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(payload)}
        if target is not None:
            view["target"] = target
        views.append(view)
        return len(views) - 1

    image_entries = []
    for image_name, payload in images:
        image_entries.append(
            {"name": image_name, "mimeType": "image/jpeg", "bufferView": add_view(payload)}
        )

    accessors = []
    attribute_map = {}
    source_primitive = source_document["meshes"][0]["primitives"][0]
    for semantic in ("POSITION", "NORMAL", "TANGENT", "TEXCOORD_0"):
        values = np.ascontiguousarray(attributes[semantic].astype(np.float32))
        view_index = add_view(values.tobytes(), 34962)
        source_accessor = source_document["accessors"][source_primitive["attributes"][semantic]]
        entry = {
            "bufferView": view_index,
            "componentType": 5126,
            "count": len(values),
            "type": source_accessor["type"],
        }
        if semantic == "POSITION":
            entry["min"] = [float(value) for value in values.min(axis=0)]
            entry["max"] = [float(value) for value in values.max(axis=0)]
        accessors.append(entry)
        attribute_map[semantic] = len(accessors) - 1

    index_dtype = np.uint16 if int(indices.max(initial=0)) <= 65535 else np.uint32
    index_component = 5123 if index_dtype is np.uint16 else 5125
    packed_indices = np.ascontiguousarray(indices.astype(index_dtype).reshape(-1))
    index_view = add_view(packed_indices.tobytes(), 34963)
    accessors.append(
        {
            "bufferView": index_view,
            "componentType": index_component,
            "count": int(packed_indices.size),
            "type": "SCALAR",
            "min": [int(packed_indices.min(initial=0))],
            "max": [int(packed_indices.max(initial=0))],
        }
    )
    index_accessor = len(accessors) - 1

    binary = b"".join(chunks)
    document = {
        "asset": {
            "version": "2.0",
            "generator": "Fatal Vow deterministic prop processor v1",
        },
        "scene": 0,
        "scenes": [{"name": name, "nodes": [0]}],
        "nodes": [{"name": name, "mesh": 0}],
        "meshes": [
            {
                "name": name,
                "primitives": [
                    {"attributes": attribute_map, "indices": index_accessor, "material": 0}
                ],
            }
        ],
        "materials": source_document.get("materials", []),
        "textures": source_document.get("textures", []),
        "samplers": source_document.get("samplers", []),
        "images": image_entries,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }
    json_chunk = pad4(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        b" ",
    )
    binary = pad4(binary)
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    payload = (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
        + struct.pack("<I4s", len(binary), b"BIN\x00")
        + binary
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def render_contact_sheet(
    records: list[dict], base_texture: Image.Image, destination: Path
) -> None:
    cell_width, cell_height = 400, 320
    canvas = Image.new("RGB", (cell_width * 4, cell_height * 3), (28, 30, 32))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    pixels = base_texture.convert("RGB")
    for index, record in enumerate(records):
        row, column = divmod(index, 4)
        x0, y0 = column * cell_width, row * cell_height
        positions = record["positions"]
        indices = record["indices"]
        uvs = record["uvs"]
        span = np.maximum(positions.max(axis=0) - positions.min(axis=0), 1e-6)
        scale = min((cell_width - 50) / span[0], (cell_height - 70) / span[1])
        projected = np.column_stack(
            [
                x0 + cell_width / 2 + positions[:, 0] * scale,
                y0 + (cell_height - 15) / 2 - positions[:, 1] * scale,
            ]
        )
        order = np.argsort(positions[indices].mean(axis=1)[:, 2])
        for triangle_index in order:
            triangle = indices[triangle_index]
            points = [tuple(projected[int(vertex)]) for vertex in triangle]
            uv = uvs[triangle].mean(axis=0)
            tx = max(0, min(pixels.width - 1, int(uv[0] * (pixels.width - 1))))
            ty = max(0, min(pixels.height - 1, int((1.0 - uv[1]) * (pixels.height - 1))))
            color = np.asarray(pixels.getpixel((tx, ty)), dtype=float)
            face = positions[triangle]
            normal = np.cross(face[1] - face[0], face[2] - face[0])
            length = float(np.linalg.norm(normal))
            light = 0.68 if length == 0 else 0.55 + 0.45 * abs(float(normal[2])) / length
            shaded = tuple(int(max(0, min(255, value * light))) for value in color)
            draw.polygon(points, fill=shaded)
        draw.rectangle((x0, y0, x0 + cell_width - 1, y0 + cell_height - 1), outline=(82, 88, 92), width=2)
        draw.text((x0 + 12, y0 + 10), record["name"], fill=(240, 240, 235), font=font)
        draw.text(
            (x0 + 12, y0 + cell_height - 28),
            f"{record['triangle_count']} triangles",
            fill=(190, 198, 202),
            font=font,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, "PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--texture-size", type=int, default=512)
    args = parser.parse_args()

    document, binary = load_glb(args.source)
    if len(document.get("nodes", [])) != 1 or len(document.get("meshes", [])) != 1:
        raise ValueError("expected the approved one-node/one-mesh Meshy batch")
    primitive = document["meshes"][0]["primitives"][0]
    attributes = {
        semantic: accessor(document, binary, accessor_index)
        for semantic, accessor_index in primitive["attributes"].items()
    }
    indices = accessor(document, binary, primitive["indices"]).reshape(-1, 3).astype(np.int64)
    positions = attributes["POSITION"]
    components = connected_components(indices, len(positions))
    x_min, y_min = positions[:, :2].min(axis=0)
    x_max, y_max = positions[:, :2].max(axis=0)
    x_edges = np.linspace(x_min, x_max, 5)
    y_edges = np.linspace(y_max, y_min, 4)
    cell_triangles: list[list[int]] = [[] for _ in PROPS]
    removed = []
    for component in components:
        component_indices = indices[component]
        vertices = np.unique(component_indices)
        center = positions[vertices].mean(axis=0)
        column = min(3, max(0, int((center[0] - x_min) / max(x_max - x_min, 1e-9) * 4)))
        row = min(2, max(0, int((y_max - center[1]) / max(y_max - y_min, 1e-9) * 3)))
        # The accepted source review identified one floating triangle immediately
        # beside the bottom-right vial.  Other one-triangle islands belong to
        # legitimate low-poly knots/edges, so the rejection must stay spatially
        # bounded instead of becoming a blanket "small component" cleanup.
        is_reviewed_vial_debris = (
            len(component) == 1
            and row == 2
            and column == 3
            and center[0] < x_edges[3] + (x_edges[4] - x_edges[3]) * 0.08
        )
        if is_reviewed_vial_debris:
            removed.append(
                {
                    "triangle_count": 1,
                    "source_triangle": int(component[0]),
                    "center": [round(float(value), 7) for value in center],
                    "reason": "isolated single-triangle debris",
                }
            )
            continue
        cell_triangles[row * 4 + column].extend(int(value) for value in component)

    original_images = []
    resized_images = []
    for image in document.get("images", []):
        view = document["bufferViews"][image["bufferView"]]
        payload = binary[view.get("byteOffset", 0) : view.get("byteOffset", 0) + view["byteLength"]]
        original_images.append((image.get("name", "texture"), payload))
        quality = 80 if image.get("name") == "normal" else 70
        resized_images.append(
            (image.get("name", "texture"), encode_jpeg(payload, args.texture_size, quality))
        )

    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for prop_index, (name, triangle_rows) in enumerate(zip(PROPS, cell_triangles)):
        if not triangle_rows:
            raise ValueError(f"no geometry assigned to {name}")
        selected = indices[np.asarray(sorted(triangle_rows), dtype=np.int64)]
        vertex_ids = np.unique(selected)
        remap = np.full(len(positions), -1, dtype=np.int64)
        remap[vertex_ids] = np.arange(len(vertex_ids))
        local_indices = remap[selected]
        local_attributes = {key: value[vertex_ids].copy() for key, value in attributes.items()}
        original_bounds_min = local_attributes["POSITION"].min(axis=0)
        original_bounds_max = local_attributes["POSITION"].max(axis=0)
        source_center = (original_bounds_min + original_bounds_max) / 2.0
        local_attributes["POSITION"] -= source_center
        output_path = args.output / f"{name}.glb"
        build_glb(name, local_attributes, local_indices, resized_images, document, output_path)
        records.append(
            {
                "name": name,
                "grid": {"row": prop_index // 4, "column": prop_index % 4},
                "path": output_path.name,
                "sha256": sha256(output_path),
                "bytes": output_path.stat().st_size,
                "triangle_count": int(len(local_indices)),
                "vertex_count": int(len(vertex_ids)),
                "source_center": [round(float(value), 7) for value in source_center],
                "source_bounds_min": [round(float(value), 7) for value in original_bounds_min],
                "source_bounds_max": [round(float(value), 7) for value in original_bounds_max],
                "origin_contract": "geometry centered on source-space axis-aligned bounds",
                "positions": local_attributes["POSITION"],
                "indices": local_indices,
                "uvs": local_attributes["TEXCOORD_0"],
            }
        )

    base_texture = Image.open(io.BytesIO(original_images[0][1]))
    contact_sheet = args.output / "prop-library-contact-sheet.png"
    render_contact_sheet(records, base_texture, contact_sheet)
    manifest_records = []
    for record in records:
        manifest_records.append({key: value for key, value in record.items() if key not in {"positions", "indices", "uvs"}})
    manifest = {
        "schema": "fatal-vow.prop-batch.v1",
        "status": "processed-candidate",
        "source": {
            "path": args.source.name,
            "sha256": sha256(args.source),
            "bytes": args.source.stat().st_size,
            "triangle_count": int(len(indices)),
            "vertex_count": int(len(positions)),
            "node_count": len(document.get("nodes", [])),
            "mesh_count": len(document.get("meshes", [])),
        },
        "processing": {
            "assignment": "disconnected components assigned to source 4x3 spatial cells",
            "texture_size": [args.texture_size, args.texture_size],
            "texture_format": "JPEG",
            "removed_components": removed,
            "removed_triangle_count": sum(item["triangle_count"] for item in removed),
            "preserved_source_triangle_count": sum(item["triangle_count"] for item in manifest_records),
        },
        "contact_sheet": {
            "path": contact_sheet.name,
            "sha256": sha256(contact_sheet),
            "bytes": contact_sheet.stat().st_size,
            "authority": "static processing evidence; human gameplay acceptance remains pending",
        },
        "props": manifest_records,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "props": len(records),
        "source_triangles": len(indices),
        "output_triangles": sum(item["triangle_count"] for item in manifest_records),
        "removed_triangles": manifest["processing"]["removed_triangle_count"],
        "output_bytes": sum(item["bytes"] for item in manifest_records),
        "manifest": str(args.output / "manifest.json"),
    }, indent=2))


if __name__ == "__main__":
    main()

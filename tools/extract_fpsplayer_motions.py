#!/usr/bin/env python3
"""Extract Infinite Brutality's complete FPSPlayer motion inventory.

Produces a compact manifest plus exact Weapon.R/Weapon.L local, model-space,
and camera-space transform samples for every embedded glTF animation clip.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from bisect import bisect_right
from pathlib import Path


COMPONENT_FORMAT = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
TYPE_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load_glb(path: Path):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2 or length != len(raw):
        raise ValueError("Expected a complete glTF 2.0 binary file")
    chunks, offset = {}, 12
    while offset < length:
        size, kind = struct.unpack_from("<II", raw, offset)
        offset += 8
        chunks[kind] = raw[offset : offset + size]
        offset += size
    return json.loads(chunks[0x4E4F534A]), chunks[0x004E4942], raw


def accessor_values(gltf, binary, index):
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    width = TYPE_WIDTH[accessor["type"]]
    fmt = COMPONENT_FORMAT[accessor["componentType"]]
    component_size = struct.calcsize("<" + fmt)
    packed_size = width * component_size
    stride = view.get("byteStride", packed_size)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    unpack = struct.Struct("<" + fmt * width).unpack_from
    values = [unpack(binary, start + i * stride) for i in range(accessor["count"])]
    return [v[0] for v in values] if width == 1 else [list(v) for v in values]


def quat_normalize(q):
    mag = math.sqrt(sum(v * v for v in q))
    return [v / mag for v in q] if mag else [0.0, 0.0, 0.0, 1.0]


def quat_slerp(a, b, amount):
    a, b = quat_normalize(a), quat_normalize(b)
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b, dot = [-v for v in b], -dot
    if dot > 0.9995:
        return quat_normalize([x + amount * (y - x) for x, y in zip(a, b)])
    theta = math.acos(max(-1.0, min(1.0, dot)))
    sin_theta = math.sin(theta)
    left = math.sin((1 - amount) * theta) / sin_theta
    right = math.sin(amount * theta) / sin_theta
    return [left * x + right * y for x, y in zip(a, b)]


def sample_channel(channel, time):
    times, values, interpolation, path = channel
    if time <= times[0]:
        return values[0]
    if time >= times[-1]:
        return values[-1]
    right = bisect_right(times, time)
    left = right - 1
    if interpolation == "STEP":
        return values[left]
    amount = (time - times[left]) / (times[right] - times[left])
    if path == "rotation":
        return quat_slerp(values[left], values[right], amount)
    return [a + amount * (b - a) for a, b in zip(values[left], values[right])]


def mat_mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def trs_matrix(t, q, s):
    x, y, z, w = quat_normalize(q)
    sx, sy, sz = s
    return [
        [(1 - 2*y*y - 2*z*z)*sx, (2*x*y - 2*z*w)*sy, (2*x*z + 2*y*w)*sz, t[0]],
        [(2*x*y + 2*z*w)*sx, (1 - 2*x*x - 2*z*z)*sy, (2*y*z - 2*x*w)*sz, t[1]],
        [(2*x*z - 2*y*w)*sx, (2*y*z + 2*x*w)*sy, (1 - 2*x*x - 2*y*y)*sz, t[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def decompose_rigid(m):
    t = [m[0][3], m[1][3], m[2][3]]
    sx = math.sqrt(sum(m[r][0] ** 2 for r in range(3)))
    sy = math.sqrt(sum(m[r][1] ** 2 for r in range(3)))
    sz = math.sqrt(sum(m[r][2] ** 2 for r in range(3)))
    r = [[m[i][j] / [sx, sy, sz][j] for j in range(3)] for i in range(3)]
    trace = r[0][0] + r[1][1] + r[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = [(r[2][1]-r[1][2])/s, (r[0][2]-r[2][0])/s, (r[1][0]-r[0][1])/s, 0.25*s]
    elif r[0][0] > r[1][1] and r[0][0] > r[2][2]:
        s = math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2]) * 2
        q = [0.25*s, (r[0][1]+r[1][0])/s, (r[0][2]+r[2][0])/s, (r[2][1]-r[1][2])/s]
    elif r[1][1] > r[2][2]:
        s = math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2]) * 2
        q = [(r[0][1]+r[1][0])/s, 0.25*s, (r[1][2]+r[2][1])/s, (r[0][2]-r[2][0])/s]
    else:
        s = math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1]) * 2
        q = [(r[0][2]+r[2][0])/s, (r[1][2]+r[2][1])/s, 0.25*s, (r[1][0]-r[0][1])/s]
    return {"translation": t, "rotation_xyzw": quat_normalize(q), "scale": [sx, sy, sz]}


def inverse_rigid(m):
    r = [[m[i][j] for j in range(3)] for i in range(3)]
    rt = [[r[j][i] for j in range(3)] for i in range(3)]
    t = [m[i][3] for i in range(3)]
    return [
        [rt[0][0], rt[0][1], rt[0][2], -sum(rt[0][i]*t[i] for i in range(3))],
        [rt[1][0], rt[1][1], rt[1][2], -sum(rt[1][i]*t[i] for i in range(3))],
        [rt[2][0], rt[2][1], rt[2][2], -sum(rt[2][i]*t[i] for i in range(3))],
        [0.0, 0.0, 0.0, 1.0],
    ]


def rounded(value):
    if isinstance(value, float):
        return round(value, 7)
    if isinstance(value, list):
        return [rounded(v) for v in value]
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    return value


def classify(name):
    if name.startswith("FistAttack") or name.startswith("FistPowerAttack"): return "fist_attack"
    if name.startswith("FistBlock") or name.startswith("FistInjured"): return "fist_defense_hurt"
    if name.startswith("FistReady") or name.startswith("FistReadied"): return "fist_ready"
    if name.startswith("FistWalk"): return "locomotion"
    if name.startswith("KnifeAttack") or name.startswith("KnifePowerAttack"): return "knife_attack"
    if name.startswith("KnifeReady") or name.startswith("KnifeReadied"): return "knife_ready"
    if name.startswith("OneHandAttack"): return "one_hand_attack"
    if name.startswith("OneHandReady") or name.startswith("OneHandReadied"): return "one_hand_ready"
    if name.startswith("WandFire"): return "wand_attack"
    if name.startswith("WandReady") or name.startswith("WandReadied"): return "wand_ready"
    if name.startswith("Climb") or name == "Mantle": return "traversal"
    if "Jump" in name or "Land" in name: return "air_locomotion"
    return "other"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("glb", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    gltf, binary, raw = load_glb(args.glb)
    args.output.mkdir(parents=True, exist_ok=True)
    nodes = gltf["nodes"]
    names = [n.get("name", f"node_{i}") for i, n in enumerate(nodes)]
    name_to_index = {name: i for i, name in enumerate(names)}
    parents = [None] * len(nodes)
    for parent, node in enumerate(nodes):
        for child in node.get("children", []): parents[child] = parent
    weapon_indices = [name_to_index[n] for n in ("Weapon.R", "Weapon.L") if n in name_to_index]
    camera_index = name_to_index.get("Camera")
    if not weapon_indices or camera_index is None:
        raise ValueError("Expected Weapon.R/Weapon.L and Camera nodes")

    accessor_cache = {}
    def values(index):
        if index not in accessor_cache: accessor_cache[index] = accessor_values(gltf, binary, index)
        return accessor_cache[index]

    clips, manifest_clips = [], []
    for animation_index, animation in enumerate(gltf.get("animations", [])):
        channel_map, all_times, interpolation_counts = {}, set(), {}
        for channel in animation.get("channels", []):
            sampler = animation["samplers"][channel["sampler"]]
            interpolation = sampler.get("interpolation", "LINEAR")
            if interpolation == "CUBICSPLINE":
                raise NotImplementedError("CUBICSPLINE is not expected in this source")
            times = values(sampler["input"])
            output = values(sampler["output"])
            node_index, path = channel["target"]["node"], channel["target"]["path"]
            channel_map[(node_index, path)] = (times, output, interpolation, path)
            all_times.update(times)
            interpolation_counts[interpolation] = interpolation_counts.get(interpolation, 0) + 1
        timeline = sorted(all_times)
        deltas = [b-a for a,b in zip(timeline, timeline[1:]) if b-a > 1e-7]
        inferred_fps = round(1/min(deltas), 6) if deltas else None

        def local_trs(node_index, time):
            node = nodes[node_index]
            t = node.get("translation", [0.0, 0.0, 0.0])
            q = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
            s = node.get("scale", [1.0, 1.0, 1.0])
            if (node_index, "translation") in channel_map: t = sample_channel(channel_map[(node_index,"translation")], time)
            if (node_index, "rotation") in channel_map: q = sample_channel(channel_map[(node_index,"rotation")], time)
            if (node_index, "scale") in channel_map: s = sample_channel(channel_map[(node_index,"scale")], time)
            return list(t), list(q), list(s)

        def world_matrix(node_index, time, cache):
            if node_index in cache: return cache[node_index]
            t, q, s = local_trs(node_index, time)
            local = trs_matrix(t, q, s)
            parent = parents[node_index]
            cache[node_index] = mat_mul(world_matrix(parent, time, cache), local) if parent is not None else local
            return cache[node_index]

        samples = []
        for time in timeline:
            cache = {}
            camera_world = world_matrix(camera_index, time, cache)
            camera_inverse = inverse_rigid(camera_world)
            weapons = {}
            for weapon_index in weapon_indices:
                local_t, local_q, local_s = local_trs(weapon_index, time)
                model_matrix = world_matrix(weapon_index, time, cache)
                camera_matrix = mat_mul(camera_inverse, model_matrix)
                weapons[names[weapon_index]] = {
                    "local": {"translation": local_t, "rotation_xyzw": local_q, "scale": local_s},
                    "model": decompose_rigid(model_matrix),
                    "camera": decompose_rigid(camera_matrix),
                }
            samples.append({"time_seconds": time, "weapons": weapons})

        animated_nodes = sorted({node for node, _ in channel_map})
        full_channels = []
        for (node_index, path), (times, output, interpolation, _) in sorted(channel_map.items()):
            full_channels.append({
                "node_index": node_index,
                "node": names[node_index],
                "path": path,
                "interpolation": interpolation,
                "times_seconds": times,
                "values": output,
            })
        clip_name = animation.get("name", f"animation_{animation_index}")
        clips.append({
            "index": animation_index,
            "name": clip_name,
            "category": classify(clip_name),
            "duration_seconds": timeline[-1] if timeline else 0.0,
            "inferred_source_fps": inferred_fps,
            "sample_count": len(timeline),
            "timeline_basis": "union of every native channel key time; no resampling",
            "interpolation_counts": interpolation_counts,
            "weapon_samples": samples,
            "full_rig_channels": full_channels,
        })
        manifest_clips.append({
            "index": animation_index, "name": clip_name, "category": classify(clip_name),
            "duration_seconds": timeline[-1] if timeline else 0.0,
            "inferred_source_fps": inferred_fps, "native_sample_count": len(timeline),
            "channel_count": len(channel_map), "animated_node_count": len(animated_nodes),
            "interpolation_counts": interpolation_counts,
        })

    basis = {
        "format": "glTF 2.0",
        "handedness": "right-handed",
        "axes": "+Y up; glTF cameras look down local -Z with +X right",
        "quaternion_order": "x,y,z,w",
        "local_space": "node transform relative to parent",
        "model_space": "source scene/model root",
        "camera_space": "Weapon transform premultiplied by inverse animated Camera world transform",
    }
    manifest = {
        "schema": "fatal-vow.infinite-brutality-motion-manifest.v1",
        "source_filename": args.glb.name,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "generator": gltf.get("asset", {}).get("generator"),
        "clip_count": len(clips),
        "weapon_nodes": [names[i] for i in weapon_indices],
        "weapon_parent_chains": {
            names[i]: list(reversed([names[j] for j in chain_to_root(i, parents)])) for i in weapon_indices
        },
        "camera_node": names[camera_index],
        "coordinate_basis": basis,
        "clips": manifest_clips,
    }
    corpus = {
        "schema": "fatal-vow.infinite-brutality-motion-corpus.v1",
        "source": {k: manifest[k] for k in ("source_filename","source_sha256","source_bytes","generator")},
        "coordinate_basis": basis,
        "clips": clips,
    }
    (args.output / "motion_manifest.json").write_text(json.dumps(rounded(manifest), indent=2) + "\n")
    (args.output / "motion_corpus.json").write_text(json.dumps(rounded(corpus), separators=(",", ":")) + "\n")
    print(json.dumps({
        "manifest": str(args.output / "motion_manifest.json"),
        "corpus": str(args.output / "motion_corpus.json"),
        "clips": len(clips),
        "manifest_bytes": (args.output / "motion_manifest.json").stat().st_size,
        "corpus_bytes": (args.output / "motion_corpus.json").stat().st_size,
    }))


def chain_to_root(index, parents):
    chain = []
    while index is not None:
        chain.append(index)
        index = parents[index]
    return chain


if __name__ == "__main__":
    main()

/**
 * Fatal Vow Exception — bounded voxel/support donor seam v0.1.
 *
 * Donor: Valar05/infinite-brutality
 * Donor ref: main @ e4d6e5b38f428e687069ebad9bb9625c503e5cc6
 * Donor file/blob: src/island-geometry.js @ fe20950ff468c077df1bf8f8532eedfcb0000c00
 * Adapted lineage: fieldIndex(), getVoxel(), setVoxel(), queryVoxelTopY(),
 * queryVoxelIntersectsPrism().
 *
 * This framework-free ES module is a portable donor carrier, not a game-engine
 * selection. It owns compact cell storage and bounded support queries only.
 * ScarCommand/ScarEvent authority remains outside this module.
 *
 * Quarantined on purpose:
 * - island, bridge, mesa, fortress, Napoleon, and sedimentary generation grammar
 * - Three.js meshes, raycasters, materials, and scene ownership
 * - TerrainLayer room rebuild/disposal lifecycle
 * - immutable stamps, global latest state, rendering, and marching geometry
 */

export const VOXEL_SUPPORT_SCHEMA_VERSION = '0.1';
export const DEFAULT_CHUNK_SIZE = 16;
export const DEFAULT_FIXED_SCALE = 1000;

export function chunkKey(chunkId) {
  return chunkId.worldId + ':' + chunkId.x + ':' + chunkId.y + ':' + chunkId.z;
}

function requireInteger(name, value, minimum = Number.MIN_SAFE_INTEGER) {
  if (!Number.isSafeInteger(value) || value < minimum) {
    throw new TypeError(name + ' must be a safe integer >= ' + minimum);
  }
}

function requireChunkId(chunkId) {
  if (!chunkId || typeof chunkId.worldId !== 'string' || !chunkId.worldId) {
    throw new TypeError('chunkId.worldId is required');
  }
  requireInteger('chunkId.x', chunkId.x);
  requireInteger('chunkId.y', chunkId.y);
  requireInteger('chunkId.z', chunkId.z);
}

export function createVoxelChunk({
  chunkId,
  sizeX = DEFAULT_CHUNK_SIZE,
  sizeY = DEFAULT_CHUNK_SIZE,
  sizeZ = DEFAULT_CHUNK_SIZE,
  cellSizeFixed = DEFAULT_FIXED_SCALE,
  originFixed = null,
  materials = null,
  revision = 0,
} = {}) {
  requireChunkId(chunkId);
  requireInteger('sizeX', sizeX, 1);
  requireInteger('sizeY', sizeY, 1);
  requireInteger('sizeZ', sizeZ, 1);
  requireInteger('cellSizeFixed', cellSizeFixed, 1);
  requireInteger('revision', revision, 0);
  const cellCount = sizeX * sizeY * sizeZ;
  if (!Number.isSafeInteger(cellCount) || cellCount > 16_777_216) {
    throw new RangeError('chunk cell count is outside the bounded carrier limit');
  }
  const resolvedOrigin = originFixed || {
    x: chunkId.x * sizeX * cellSizeFixed,
    y: chunkId.y * sizeY * cellSizeFixed,
    z: chunkId.z * sizeZ * cellSizeFixed,
  };
  requireInteger('originFixed.x', resolvedOrigin.x);
  requireInteger('originFixed.y', resolvedOrigin.y);
  requireInteger('originFixed.z', resolvedOrigin.z);
  const cells = materials == null ? new Uint16Array(cellCount) : new Uint16Array(materials);
  if (cells.length !== cellCount) throw new RangeError('material storage length does not match chunk bounds');
  return {
    schemaVersion: VOXEL_SUPPORT_SCHEMA_VERSION,
    chunkId: Object.freeze({ ...chunkId }),
    key: chunkKey(chunkId),
    sizeX,
    sizeY,
    sizeZ,
    cellSizeFixed,
    originFixed: Object.freeze({ ...resolvedOrigin }),
    revision,
    materials: cells,
  };
}

export function cellIndex(chunk, x, y, z) {
  return x + chunk.sizeX * (y + chunk.sizeY * z);
}

export function inBounds(chunk, x, y, z) {
  return x >= 0 && y >= 0 && z >= 0
    && x < chunk.sizeX && y < chunk.sizeY && z < chunk.sizeZ;
}

export function getMaterial(chunk, x, y, z) {
  if (!inBounds(chunk, x, y, z)) return 0;
  return chunk.materials[cellIndex(chunk, x, y, z)];
}

function canonicalCellOrder(a, b) {
  return a.z - b.z || a.y - b.y || a.x - b.x;
}

export function stageChunkWrites(chunk, expectedRevision, writes) {
  requireInteger('expectedRevision', expectedRevision, 0);
  if (chunk.revision !== expectedRevision) {
    return {
      accepted: false,
      reason: 'STALE_REVISION',
      chunkKey: chunk.key,
      observedRevision: chunk.revision,
      expectedRevision,
    };
  }
  const ordered = [...writes].sort(canonicalCellOrder);
  const seen = new Set();
  for (const write of ordered) {
    requireInteger('write.x', write.x);
    requireInteger('write.y', write.y);
    requireInteger('write.z', write.z);
    requireInteger('write.material', write.material, 0);
    if (write.material > 65_535) throw new RangeError('material must fit Uint16 storage');
    if (!inBounds(chunk, write.x, write.y, write.z)) {
      return { accepted: false, reason: 'OUT_OF_RANGE', chunkKey: chunk.key };
    }
    const key = write.x + ':' + write.y + ':' + write.z;
    if (seen.has(key)) {
      return { accepted: false, reason: 'DUPLICATE_CELL_WRITE', chunkKey: chunk.key };
    }
    seen.add(key);
  }
  const nextMaterials = chunk.materials.slice();
  let changed = false;
  for (const write of ordered) {
    const index = cellIndex(chunk, write.x, write.y, write.z);
    if (nextMaterials[index] !== write.material) {
      nextMaterials[index] = write.material;
      changed = true;
    }
  }
  return {
    accepted: true,
    chunkKey: chunk.key,
    revisionBefore: chunk.revision,
    revisionAfter: changed ? chunk.revision + 1 : chunk.revision,
    changed,
    nextMaterials,
  };
}

export function applyAtomicChunkTransaction(chunksByKey, edits, expectedRevisions) {
  const orderedEdits = [...edits].sort((a, b) => a.chunkKey.localeCompare(b.chunkKey));
  const seenChunks = new Set();
  const staged = [];
  for (const edit of orderedEdits) {
    if (seenChunks.has(edit.chunkKey)) {
      return { accepted: false, reason: 'DUPLICATE_CHUNK_EDIT', committed: [] };
    }
    seenChunks.add(edit.chunkKey);
    const chunk = chunksByKey.get(edit.chunkKey);
    if (!chunk) return { accepted: false, reason: 'UNKNOWN_CHUNK', committed: [] };
    const expected = expectedRevisions[edit.chunkKey];
    const candidate = stageChunkWrites(chunk, expected, edit.writes);
    if (!candidate.accepted) return { ...candidate, committed: [] };
    staged.push({ chunk, candidate });
  }
  for (const { chunk, candidate } of staged) {
    chunk.materials = candidate.nextMaterials;
    chunk.revision = candidate.revisionAfter;
  }
  return {
    accepted: true,
    committed: staged.filter(({ candidate }) => candidate.changed).map(({ chunk, candidate }) => ({
      chunkKey: chunk.key,
      revisionBefore: candidate.revisionBefore,
      revisionAfter: candidate.revisionAfter,
    })),
  };
}

function floorDiv(value, divisor) {
  return Math.floor(value / divisor);
}

function clampedCellRange(chunk, centerFixed, radiusFixed, axis) {
  requireInteger('centerFixed', centerFixed);
  requireInteger('radiusFixed', radiusFixed, 0);
  const origin = chunk.originFixed[axis];
  const size = axis === 'x' ? chunk.sizeX : chunk.sizeZ;
  return {
    minimum: Math.max(0, floorDiv(centerFixed - radiusFixed - origin, chunk.cellSizeFixed)),
    maximum: Math.min(size - 1, floorDiv(centerFixed + radiusFixed - origin, chunk.cellSizeFixed)),
  };
}

export function queryVoxelTopFixed(chunk, xFixed, zFixed, radiusFixed = 0) {
  const xRange = clampedCellRange(chunk, xFixed, radiusFixed, 'x');
  const zRange = clampedCellRange(chunk, zFixed, radiusFixed, 'z');
  if (xRange.minimum > xRange.maximum || zRange.minimum > zRange.maximum) return null;
  let best = null;
  for (let z = zRange.minimum; z <= zRange.maximum; z += 1) {
    for (let x = xRange.minimum; x <= xRange.maximum; x += 1) {
      for (let y = chunk.sizeY - 1; y >= 0; y -= 1) {
        if (getMaterial(chunk, x, y, z) === 0) continue;
        const topFixed = chunk.originFixed.y + (y + 1) * chunk.cellSizeFixed;
        if (best == null || topFixed > best) best = topFixed;
        break;
      }
    }
  }
  return best;
}

export function queryVoxelIntersectsPrismFixed(
  chunk,
  xFixed,
  zFixed,
  minYFixed,
  maxYFixed,
  radiusFixed = 0,
) {
  requireInteger('minYFixed', minYFixed);
  requireInteger('maxYFixed', maxYFixed);
  if (maxYFixed < minYFixed) throw new RangeError('maxYFixed must be >= minYFixed');
  const xRange = clampedCellRange(chunk, xFixed, radiusFixed, 'x');
  const zRange = clampedCellRange(chunk, zFixed, radiusFixed, 'z');
  const y0 = Math.max(0, floorDiv(minYFixed - chunk.originFixed.y, chunk.cellSizeFixed));
  const y1 = Math.min(chunk.sizeY - 1, floorDiv(maxYFixed - chunk.originFixed.y, chunk.cellSizeFixed));
  if (xRange.minimum > xRange.maximum || zRange.minimum > zRange.maximum || y0 > y1) return false;
  for (let z = zRange.minimum; z <= zRange.maximum; z += 1) {
    for (let x = xRange.minimum; x <= xRange.maximum; x += 1) {
      for (let y = y0; y <= y1; y += 1) {
        if (getMaterial(chunk, x, y, z) !== 0) return true;
      }
    }
  }
  return false;
}

export function runVoxelSupportDonorTests() {
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const a = createVoxelChunk({ chunkId: { worldId: 'w', x: 0, y: 0, z: 0 }, sizeX: 4, sizeY: 4, sizeZ: 4 });
  const b = createVoxelChunk({ chunkId: { worldId: 'w', x: 1, y: 0, z: 0 }, sizeX: 4, sizeY: 4, sizeZ: 4 });
  const chunks = new Map([[a.key, a], [b.key, b]]);
  const rejected = applyAtomicChunkTransaction(chunks, [
    { chunkKey: a.key, writes: [{ x: 1, y: 1, z: 1, material: 1 }] },
    { chunkKey: b.key, writes: [{ x: 99, y: 1, z: 1, material: 1 }] },
  ], { [a.key]: 0, [b.key]: 0 });
  assert(!rejected.accepted && a.revision === 0 && b.revision === 0, 'cross-chunk refusal mutated truth');
  const accepted = applyAtomicChunkTransaction(chunks, [
    { chunkKey: a.key, writes: [{ x: 1, y: 1, z: 1, material: 4 }] },
    { chunkKey: b.key, writes: [{ x: 0, y: 2, z: 0, material: 7 }] },
  ], { [a.key]: 0, [b.key]: 0 });
  assert(accepted.accepted && a.revision === 1 && b.revision === 1, 'atomic commit revisions are wrong');
  assert(getMaterial(a, 1, 1, 1) === 4 && getMaterial(a, -1, 0, 0) === 0, 'bounded material lookup failed');
  assert(queryVoxelTopFixed(a, 1500, 1500) === 2000, 'highest support lookup failed');
  assert(queryVoxelIntersectsPrismFixed(a, 1500, 1500, 1000, 1999), 'prism intersection missed solid');
  assert(!queryVoxelIntersectsPrismFixed(a, 1500, 1500, 2001, 2999), 'prism intersection invented solid');
  return {
    passed: 6,
    chunkBytes: a.materials.byteLength,
    cellsPerChunk: a.materials.length,
    revisions: [a.revision, b.revision],
  };
}

if (typeof process !== 'undefined' && process.argv?.[1]?.endsWith('voxel_support_v0_1.mjs')) {
  const result = runVoxelSupportDonorTests();
  console.log(JSON.stringify(result));
}

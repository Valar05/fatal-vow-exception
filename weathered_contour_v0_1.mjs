/**
 * Fatal Vow Exception — cached weathered contour presentation v0.1.
 *
 * This module derives display geometry from authoritative voxel chunks. It may
 * cache, tint, simplify, and discard meshes. It may never write voxel truth.
 * Revision-tagged jobs are the only admission path; stale output is refused.
 */

import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import {
  applyAtomicChunkTransaction,
  cellIndex,
  createVoxelChunk,
  getMaterial,
} from './voxel_support_v0_1.mjs';

export const CONTOUR_SCHEMA_VERSION = '0.1';

export const CONTOUR_PROFILES = Object.freeze({
  'tim-phone-low': Object.freeze({ maxQuads: 4096, svgScale: 9, label: 'Tim phone / low' }),
  'high-quality': Object.freeze({ maxQuads: 16384, svgScale: 10, label: 'High quality' }),
});

const FACE_SHADE = Object.freeze({
  '0:1': 0.78,
  '0:-1': 0.42,
  '1:1': 1.0,
  '1:-1': 0.34,
  '2:1': 0.66,
  '2:-1': 0.48,
});

function canonicalJson(value) {
  if (value && ArrayBuffer.isView(value)) value = [...value];
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map((key) => JSON.stringify(key) + ':' + canonicalJson(value[key])).join(',') + '}';
  }
  return JSON.stringify(value);
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

export function chunkTruthHash(chunk) {
  return sha256(canonicalJson({
    key: chunk.key,
    revision: chunk.revision,
    size: [chunk.sizeX, chunk.sizeY, chunk.sizeZ],
    materials: chunk.materials,
  }));
}

function maskSame(a, b) {
  return a != null && b != null && a.material === b.material && a.sign === b.sign;
}

/** Greedy voxel surface extraction. Output coordinates remain integer cell units. */
export function buildWeatheredContour(chunk, profileName = 'tim-phone-low') {
  const profile = CONTOUR_PROFILES[profileName];
  if (!profile) throw new Error('unknown contour profile: ' + profileName);
  const truthBefore = chunkTruthHash(chunk);
  const dims = [chunk.sizeX, chunk.sizeY, chunk.sizeZ];
  const quads = [];
  const x = [0, 0, 0];
  const q = [0, 0, 0];

  for (let d = 0; d < 3; d += 1) {
    const u = (d + 1) % 3;
    const v = (d + 2) % 3;
    q.fill(0);
    q[d] = 1;
    const mask = new Array(dims[u] * dims[v]);
    x[d] = -1;
    while (x[d] < dims[d]) {
      let n = 0;
      for (x[v] = 0; x[v] < dims[v]; x[v] += 1) {
        for (x[u] = 0; x[u] < dims[u]; x[u] += 1) {
          const a = x[d] >= 0 ? getMaterial(chunk, x[0], x[1], x[2]) : 0;
          const b = x[d] < dims[d] - 1
            ? getMaterial(chunk, x[0] + q[0], x[1] + q[1], x[2] + q[2]) : 0;
          mask[n] = (a !== 0) === (b !== 0)
            ? null
            : (a !== 0 ? { material: a, sign: 1 } : { material: b, sign: -1 });
          n += 1;
        }
      }
      x[d] += 1;
      n = 0;
      for (let j = 0; j < dims[v]; j += 1) {
        for (let i = 0; i < dims[u];) {
          const cell = mask[n];
          if (cell == null) { i += 1; n += 1; continue; }
          let width = 1;
          while (i + width < dims[u] && maskSame(mask[n + width], cell)) width += 1;
          let height = 1;
          outer: for (; j + height < dims[v]; height += 1) {
            for (let k = 0; k < width; k += 1) {
              if (!maskSame(mask[n + k + height * dims[u]], cell)) break outer;
            }
          }
          x[u] = i;
          x[v] = j;
          const du = [0, 0, 0];
          const dv = [0, 0, 0];
          du[u] = width;
          dv[v] = height;
          const base = [...x];
          let vertices = [
            base,
            base.map((value, axis) => value + du[axis]),
            base.map((value, axis) => value + du[axis] + dv[axis]),
            base.map((value, axis) => value + dv[axis]),
          ];
          if (cell.sign < 0) vertices = [vertices[0], vertices[3], vertices[2], vertices[1]];
          quads.push(Object.freeze({
            material: cell.material,
            normalAxis: d,
            normalSign: cell.sign,
            width,
            height,
            vertices: Object.freeze(vertices.map((point) => Object.freeze(point))),
          }));
          for (let l = 0; l < height; l += 1) {
            for (let k = 0; k < width; k += 1) mask[n + k + l * dims[u]] = null;
          }
          i += width;
          n += width;
        }
      }
    }
  }
  if (quads.length > profile.maxQuads) {
    return Object.freeze({ accepted: false, reason: 'PROFILE_QUAD_BUDGET', sourceRevision: chunk.revision, quadCount: quads.length });
  }
  if (chunkTruthHash(chunk) !== truthBefore) throw new Error('presentation mutated authoritative chunk truth');
  return Object.freeze({
    accepted: true,
    schemaVersion: CONTOUR_SCHEMA_VERSION,
    chunkKey: chunk.key,
    sourceRevision: chunk.revision,
    profileName,
    truthHash: truthBefore,
    quads: Object.freeze(quads),
    quadCount: quads.length,
    triangleCount: quads.length * 2,
  });
}

export class ContourMeshCache {
  constructor(profileName = 'tim-phone-low') {
    if (!CONTOUR_PROFILES[profileName]) throw new Error('unknown contour profile: ' + profileName);
    this.profileName = profileName;
    this.entries = new Map();
    this.buildCount = 0;
  }

  consume(job, chunksByKey) {
    if (!job || job.rendererProfile !== this.profileName) {
      return Object.freeze({ accepted: false, reason: 'WRONG_PROFILE' });
    }
    const chunk = chunksByKey.get(job.chunkKey);
    if (!chunk) return Object.freeze({ accepted: false, reason: 'UNKNOWN_CHUNK' });
    if (chunk.revision !== job.sourceRevision) {
      return Object.freeze({ accepted: false, reason: 'STALE_REVISION', observedRevision: chunk.revision });
    }
    const cacheKey = job.chunkKey + '@' + job.sourceRevision;
    if (this.entries.has(cacheKey)) return Object.freeze({ accepted: true, cacheHit: true, mesh: this.entries.get(cacheKey) });
    const mesh = buildWeatheredContour(chunk, this.profileName);
    if (!mesh.accepted) return mesh;
    this.entries.set(cacheKey, mesh);
    this.buildCount += 1;
    for (const key of [...this.entries.keys()]) {
      if (key.startsWith(job.chunkKey + '@') && key !== cacheKey) this.entries.delete(key);
    }
    return Object.freeze({ accepted: true, cacheHit: false, mesh });
  }
}

function colorFor(material, normalAxis, normalSign, seed) {
  const bases = {
    1: [111, 82, 49],
    2: [78, 73, 58],
    3: [56, 47, 35],
  };
  const base = bases[material] ?? [103, 79, 52];
  const jitter = ((seed * 17 + material * 31) % 15) - 7;
  const shade = FACE_SHADE[normalAxis + ':' + normalSign] ?? 0.6;
  return 'rgb(' + base.map((channel) => Math.max(0, Math.min(255, Math.round(channel * shade + jitter)))).join(' ') + ')';
}

function escapeXml(value) {
  return String(value).replace(/[&<>\"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[char]);
}

function project(point, ox, oy, scale) {
  const [x, y, z] = point;
  return [ox + (x - z) * scale, oy + (x + z) * scale * 0.48 - y * scale];
}

function meshPolygons(mesh, ox, oy, scale) {
  return mesh.quads
    .filter((quad) => (quad.normalAxis === 1 && quad.normalSign > 0)
      || (quad.normalAxis === 0 && quad.normalSign > 0)
      || (quad.normalAxis === 2 && quad.normalSign > 0))
    .map((quad, index) => {
      const centroid = quad.vertices.reduce((sum, point) => sum.map((value, axis) => value + point[axis]), [0, 0, 0]).map((v) => v / 4);
      return {
        depth: centroid[0] + centroid[2] - centroid[1] * 0.2,
        points: quad.vertices.map((point) => project(point, ox, oy, scale)).map((p) => p.join(',')).join(' '),
        fill: colorFor(quad.material, quad.normalAxis, quad.normalSign, index),
      };
    })
    .sort((a, b) => a.depth - b.depth)
    .map((polygon) => '<polygon points="' + polygon.points + '" fill="' + polygon.fill + '" stroke="#231b13" stroke-width="0.7"/>')
    .join('');
}

function fixtureChunk() {
  const chunk = createVoxelChunk({
    chunkId: { worldId: 'chapter-9-clearing', x: 0, y: 0, z: 0 },
    sizeX: 12, sizeY: 7, sizeZ: 10,
  });
  for (let z = 0; z < chunk.sizeZ; z += 1) {
    for (let x = 0; x < chunk.sizeX; x += 1) {
      const top = 2 + ((x * 7 + z * 11) % 5 === 0 ? 1 : 0);
      for (let y = 0; y <= top; y += 1) chunk.materials[cellIndex(chunk, x, y, z)] = y === top ? 1 : 3;
    }
  }
  return chunk;
}

function cloneChunk(chunk) {
  return createVoxelChunk({
    chunkId: chunk.chunkId,
    sizeX: chunk.sizeX,
    sizeY: chunk.sizeY,
    sizeZ: chunk.sizeZ,
    cellSizeFixed: chunk.cellSizeFixed,
    originFixed: chunk.originFixed,
    materials: chunk.materials,
    revision: chunk.revision,
  });
}

export function buildChapter9ContourWitness() {
  const before = fixtureChunk();
  const after = cloneChunk(before);
  const removals = [];
  const additions = [];
  for (let z = 2; z <= 7; z += 1) {
    const trenchX = 5 + (z > 4 ? 1 : 0);
    for (let y = 2; y <= 3; y += 1) {
      const material = getMaterial(after, trenchX, y, z);
      if (material) removals.push({ x: trenchX, y, z, material });
    }
  }
  removals.forEach((cell, index) => additions.push({
    x: index % 2 === 0 ? 3 : 8,
    y: 4 + Math.floor(index / 8),
    z: 2 + (index % 6),
    material: cell.material,
  }));
  const transaction = applyAtomicChunkTransaction(
    new Map([[after.key, after]]),
    [{ chunkKey: after.key, writes: [
      ...removals.map(({ x, y, z }) => ({ x, y, z, material: 0 })),
      ...additions,
    ] }],
    { [after.key]: 0 },
  );
  if (!transaction.accepted) throw new Error('fixture shovel transaction failed: ' + transaction.reason);
  const beforeMesh = buildWeatheredContour(before);
  const afterMesh = buildWeatheredContour(after);
  return Object.freeze({ before, after, beforeMesh, afterMesh, movedCells: removals.length, transaction });
}

export function buildChapter9ContourDemoSvg() {
  const witness = buildChapter9ContourWitness();
  const width = 1200;
  const height = 680;
  const panel = (x, title, subtitle, mesh) => [
    '<g>',
    '<rect x="' + x + '" y="92" width="540" height="455" rx="18" fill="#171714" stroke="#746044"/>',
    '<text x="' + (x + 28) + '" y="132" class="panelTitle">' + escapeXml(title) + '</text>',
    '<text x="' + (x + 28) + '" y="158" class="small">' + escapeXml(subtitle) + '</text>',
    meshPolygons(mesh, x + 270, 355, 22),
    '<text x="' + (x + 28) + '" y="520" class="metric">' + mesh.quadCount + ' cached quads · ' + mesh.triangleCount + ' triangles</text>',
    '</g>',
  ].join('');
  return [
    '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '" viewBox="0 0 ' + width + ' ' + height + '">',
    '<rect width="1200" height="680" fill="#0d0d0b"/>',
    '<style>text{font-family:system-ui,sans-serif;fill:#eadfc9}.title{font-size:30px;font-weight:800}.panelTitle{font-size:21px;font-weight:750}.small{font-size:14px;fill:#b9aa8e}.metric{font-size:14px;font-weight:700;fill:#d4bd91}.law{font-size:16px;font-style:italic;fill:#d7c9ae}</style>',
    '<text x="60" y="52" class="title">Fatal Vow Exception — the first visible scar</text>',
    panel(40, 'Revision 0 — held earth', 'Authoritative cells before the shovel stroke', witness.beforeMesh),
    panel(620, 'Revision 1 — cut and spoil', witness.movedCells + ' cells moved; none created or erased', witness.afterMesh),
    '<rect x="40" y="575" width="1120" height="68" rx="12" fill="#231d15" stroke="#746044"/>',
    '<text x="65" y="605" class="law">The visible earth is disposable. The scar beneath it is not.</text>',
    '<text x="65" y="629" class="small">Profile: Tim phone / low · greedy contour extraction · revision-tagged cache · stale work rejected</text>',
    '</svg>',
  ].join('');
}

export function runWeatheredContourTests() {
  let passed = 0;
  const test = (fn) => { fn(); passed += 1; };

  test(() => {
    const chunk = createVoxelChunk({ chunkId: { worldId: 'test', x: 0, y: 0, z: 0 }, sizeX: 4, sizeY: 4, sizeZ: 4 });
    chunk.materials.fill(1);
    const mesh = buildWeatheredContour(chunk);
    assert.equal(mesh.quadCount, 6, 'greedy meshing must collapse a solid prism to six quads');
  });
  test(() => {
    const witness = buildChapter9ContourWitness();
    assert.equal(witness.transaction.committed[0].revisionAfter, 1);
    assert.equal(witness.before.materials.reduce((a, b) => a + (b !== 0), 0), witness.after.materials.reduce((a, b) => a + (b !== 0), 0));
    assert.notEqual(witness.beforeMesh.truthHash, witness.afterMesh.truthHash);
  });
  test(() => {
    const chunk = fixtureChunk();
    const before = chunkTruthHash(chunk);
    buildWeatheredContour(chunk);
    assert.equal(chunkTruthHash(chunk), before, 'presentation must not mutate truth');
  });
  test(() => {
    const chunk = fixtureChunk();
    const chunks = new Map([[chunk.key, chunk]]);
    const cache = new ContourMeshCache('tim-phone-low');
    const job = { chunkKey: chunk.key, sourceRevision: 0, rendererProfile: 'tim-phone-low' };
    assert.equal(cache.consume(job, chunks).cacheHit, false);
    assert.equal(cache.consume(job, chunks).cacheHit, true);
    assert.equal(cache.buildCount, 1);
  });
  test(() => {
    const chunk = fixtureChunk();
    const cache = new ContourMeshCache('tim-phone-low');
    const job = { chunkKey: chunk.key, sourceRevision: 0, rendererProfile: 'tim-phone-low' };
    chunk.revision = 1;
    assert.equal(cache.consume(job, new Map([[chunk.key, chunk]])).reason, 'STALE_REVISION');
  });
  test(() => {
    const chunk = fixtureChunk();
    const cache = new ContourMeshCache('tim-phone-low');
    const job = { chunkKey: chunk.key, sourceRevision: 0, rendererProfile: 'high-quality' };
    assert.equal(cache.consume(job, new Map([[chunk.key, chunk]])).reason, 'WRONG_PROFILE');
  });
  test(() => {
    const svgA = buildChapter9ContourDemoSvg();
    const svgB = buildChapter9ContourDemoSvg();
    assert.equal(svgA, svgB, 'visible witness must be deterministic');
    assert.match(svgA, /Revision 1 — cut and spoil/);
    assert.match(svgA, /none created or erased/);
  });
  test(() => {
    const witness = buildChapter9ContourWitness();
    assert.ok(witness.afterMesh.quadCount < CONTOUR_PROFILES['tim-phone-low'].maxQuads);
    assert.equal(witness.afterMesh.profileName, 'tim-phone-low');
  });

  return Object.freeze({
    passed,
    contourFixtures: 8,
    demoSvgSha256: sha256(buildChapter9ContourDemoSvg()),
    law: 'visible earth is disposable; authoritative scars are not',
  });
}

if (process.argv[1]?.endsWith('weathered_contour_v0_1.mjs')) {
  console.log(JSON.stringify(runWeatheredContourTests()));
}

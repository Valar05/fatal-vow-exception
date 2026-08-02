/**
 * Fatal Vow Exception — scar/voxel authority bridge v0.1.
 *
 * This is an engine-neutral executable contract. It binds accepted ScarCommands
 * to the bounded voxel carrier without allowing meshes, animation, renderer
 * quality, or input source to become simulation authority.
 *
 * Implemented now:
 * - MOVE_MATERIAL as one atomic cross-chunk shovel transaction
 * - exact cell/material conservation and monotonic chunk revisions
 * - append-only hash-chained events and preserved refusals
 * - caller command idempotency and network-shaped expected revisions
 * - canonical snapshot/load/replay with tamper rejection
 * - coalesced dirty-chunk work, one remesh issue per frame, stale rejection
 * - Momo-chan refusal, accessible refusal text, and novel-canon firewall
 *
 * Deliberately absent:
 * - generated meshes or collision presentation
 * - Godot/runtime binding, networking, prediction, rollback, or reconciliation
 * - island/Napoleon grammar, immutable stamps, or disposal lifecycle
 * - procedural animation deciding whether a shovel act succeeds
 */

import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import {
  applyAtomicChunkTransaction,
  cellIndex,
  createVoxelChunk,
  getMaterial,
  inBounds,
} from './voxel_support_v0_1.mjs';

export const SCAR_VOXEL_SCHEMA_VERSION = '0.1';
export const RULESET_VERSION = 'scar-voxel-0.1';

export const NarrativeSurface = Object.freeze({
  GAME_ONLY: 'GAME_ONLY',
  SIMULATION_RECORD: 'SIMULATION_RECORD',
  PLAYER_HISTORY: 'PLAYER_HISTORY',
  PROPOSED_STORY_EVIDENCE: 'PROPOSED_STORY_EVIDENCE',
});

export const RefusalReason = Object.freeze({
  STALE_REVISION: 'STALE_REVISION',
  OUT_OF_RANGE: 'OUT_OF_RANGE',
  MATERIAL_BLOCKED: 'MATERIAL_BLOCKED',
  ACTOR_REFUSED: 'ACTOR_REFUSED',
  AUTHORITY_DENIED: 'AUTHORITY_DENIED',
  SCHEMA_UNSUPPORTED: 'SCHEMA_UNSUPPORTED',
  INVALID_COMMAND: 'INVALID_COMMAND',
  MATERIAL_NOT_CONSERVED: 'MATERIAL_NOT_CONSERVED',
});

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function requireString(name, value) {
  if (typeof value !== 'string' || value.length === 0) {
    throw new TypeError(name + ' must be a non-empty string');
  }
}

function requireSafeInteger(name, value, minimum = Number.MIN_SAFE_INTEGER) {
  if (!Number.isSafeInteger(value) || value < minimum) {
    throw new TypeError(name + ' must be a safe integer >= ' + minimum);
  }
}

function sortedObject(entries) {
  return Object.fromEntries([...entries].sort(([a], [b]) => a.localeCompare(b)));
}

export function canonicalJson(value) {
  if (value instanceof Uint16Array) return canonicalJson([...value]);
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  if (isRecord(value)) {
    return '{' + Object.keys(value).sort().map((key) => (
      JSON.stringify(key) + ':' + canonicalJson(value[key])
    )).join(',') + '}';
  }
  return JSON.stringify(value);
}

export function hashCanonical(value) {
  return createHash('sha256').update(canonicalJson(value)).digest('hex');
}

function cellKey(cell) {
  return cell.chunkKey + ':' + cell.x + ':' + cell.y + ':' + cell.z;
}

function compareCells(a, b) {
  return a.chunkKey.localeCompare(b.chunkKey)
    || a.z - b.z || a.y - b.y || a.x - b.x || a.material - b.material;
}

function normalizeCell(name, cell) {
  if (!isRecord(cell)) throw new TypeError(name + ' must be an object');
  requireString(name + '.chunkKey', cell.chunkKey);
  requireSafeInteger(name + '.x', cell.x);
  requireSafeInteger(name + '.y', cell.y);
  requireSafeInteger(name + '.z', cell.z);
  requireSafeInteger(name + '.material', cell.material, 1);
  if (cell.material > 65_535) throw new RangeError(name + '.material exceeds Uint16');
  return Object.freeze({
    chunkKey: cell.chunkKey,
    x: cell.x,
    y: cell.y,
    z: cell.z,
    material: cell.material,
  });
}

function normalizeCommand(command) {
  if (!isRecord(command)) throw new TypeError('command must be an object');
  for (const name of ['schemaVersion', 'worldId', 'commandId', 'issuedByActorId',
    'effectiveActorId', 'operation', 'declaredIntent']) {
    requireString(name, command[name]);
  }
  requireSafeInteger('simulationTick', command.simulationTick, 0);
  if (!Array.isArray(command.targetChunkKeys) || command.targetChunkKeys.length === 0) {
    throw new TypeError('targetChunkKeys must be a non-empty array');
  }
  const targetChunkKeys = [...new Set(command.targetChunkKeys)];
  if (targetChunkKeys.length !== command.targetChunkKeys.length) {
    throw new TypeError('targetChunkKeys cannot contain duplicates');
  }
  targetChunkKeys.forEach((key, index) => requireString('targetChunkKeys[' + index + ']', key));
  if (!isRecord(command.expectedChunkRevisions)) {
    throw new TypeError('expectedChunkRevisions must be an object');
  }
  for (const key of targetChunkKeys) {
    requireSafeInteger('expectedChunkRevisions[' + key + ']', command.expectedChunkRevisions[key], 0);
  }
  const parameters = isRecord(command.parameters) ? structuredClone(command.parameters) : {};
  const accessibilityInputSource = command.accessibilityInputSource ?? null;
  if (accessibilityInputSource !== null) requireString('accessibilityInputSource', accessibilityInputSource);
  return Object.freeze({
    schemaVersion: command.schemaVersion,
    worldId: command.worldId,
    commandId: command.commandId,
    issuedByActorId: command.issuedByActorId,
    effectiveActorId: command.effectiveActorId,
    toolId: command.toolId ?? null,
    operation: command.operation,
    targetChunkKeys: Object.freeze([...targetChunkKeys].sort()),
    expectedChunkRevisions: Object.freeze({ ...command.expectedChunkRevisions }),
    parameters: Object.freeze(parameters),
    simulationTick: command.simulationTick,
    declaredIntent: command.declaredIntent,
    causalParentEventIds: Object.freeze([...(command.causalParentEventIds ?? [])]),
    accessibilityInputSource,
  });
}

function cloneChunk(chunk) {
  return createVoxelChunk({
    chunkId: { ...chunk.chunkId },
    sizeX: chunk.sizeX,
    sizeY: chunk.sizeY,
    sizeZ: chunk.sizeZ,
    cellSizeFixed: chunk.cellSizeFixed,
    originFixed: { ...chunk.originFixed },
    materials: chunk.materials,
    revision: chunk.revision,
  });
}

function chunkRecord(chunk) {
  return {
    chunkId: { ...chunk.chunkId },
    sizeX: chunk.sizeX,
    sizeY: chunk.sizeY,
    sizeZ: chunk.sizeZ,
    cellSizeFixed: chunk.cellSizeFixed,
    originFixed: { ...chunk.originFixed },
    revision: chunk.revision,
    materials: [...chunk.materials],
  };
}

function rejectionText(reason, detail) {
  const actions = {
    STALE_REVISION: 'The ground changed. Refresh this cut and try again.',
    OUT_OF_RANGE: 'This cut leaves the loaded ground. Choose a cell inside the marked chunk.',
    MATERIAL_BLOCKED: 'The shovel cannot move that material. Inspect the obstruction or choose another cut.',
    ACTOR_REFUSED: detail,
    AUTHORITY_DENIED: 'Runtime action cannot assign novel canon. Record it on an allowed game surface.',
    SCHEMA_UNSUPPORTED: 'Update the command schema before trying this action again.',
    INVALID_COMMAND: 'The shovel instruction is incomplete. Choose a valid source and spoil destination.',
    MATERIAL_NOT_CONSERVED: 'The cut would create or erase material. Pair every removed cell with matching spoil.',
  };
  return actions[reason] ?? detail;
}

export class DirtyChunkQueue {
  constructor(authority, rendererProfile) {
    requireString('rendererProfile', rendererProfile);
    this.authority = authority;
    this.rendererProfile = rendererProfile;
    this.pendingByChunk = new Map();
    this.issuedThisFrame = 0;
  }

  beginFrame() {
    this.issuedThisFrame = 0;
  }

  mark(chunkKey, sourceRevision) {
    requireString('chunkKey', chunkKey);
    requireSafeInteger('sourceRevision', sourceRevision, 0);
    this.pendingByChunk.set(chunkKey, Object.freeze({
      chunkKey,
      sourceRevision,
      rendererProfile: this.rendererProfile,
      jobKey: chunkKey + '@' + sourceRevision + '@' + this.rendererProfile,
    }));
  }

  issueOne() {
    if (this.issuedThisFrame >= 1) return null;
    const key = [...this.pendingByChunk.keys()].sort()[0];
    if (key === undefined) return null;
    const job = this.pendingByChunk.get(key);
    this.pendingByChunk.delete(key);
    this.issuedThisFrame += 1;
    return job;
  }

  acceptResult(job) {
    if (!job || job.rendererProfile !== this.rendererProfile) return false;
    const chunk = this.authority.chunks.get(job.chunkKey);
    return Boolean(chunk && chunk.revision === job.sourceRevision);
  }
}

export class ScarVoxelAuthority {
  constructor(worldId = 'chapter-9') {
    requireString('worldId', worldId);
    this.worldId = worldId;
    this.chunks = new Map();
    this.events = [];
    this.refusals = [];
    this.scars = new Map();
    this.commandResults = new Map();
    this.presentationQueues = new Set();
    this.integrityHead = 'GENESIS';
  }

  addChunk(chunk) {
    if (chunk.chunkId.worldId !== this.worldId) throw new Error('chunk belongs to another world');
    if (this.chunks.has(chunk.key)) throw new Error('duplicate chunk: ' + chunk.key);
    this.chunks.set(chunk.key, cloneChunk(chunk));
  }

  createPresentationQueue(rendererProfile) {
    const queue = new DirtyChunkQueue(this, rendererProfile);
    this.presentationQueues.add(queue);
    return queue;
  }

  authoritativeRecord() {
    return {
      schemaVersion: SCAR_VOXEL_SCHEMA_VERSION,
      rulesetVersion: RULESET_VERSION,
      worldId: this.worldId,
      chunks: sortedObject([...this.chunks].map(([key, chunk]) => [key, chunkRecord(chunk)])),
      events: structuredClone(this.events),
      refusals: structuredClone(this.refusals),
      scars: sortedObject([...this.scars].map(([key, scar]) => [key, structuredClone(scar)])),
      commandResults: sortedObject([...this.commandResults].map(([key, value]) => [key, structuredClone(value)])),
      integrityHead: this.integrityHead,
    };
  }

  authorityHash() {
    return hashCanonical(this.authoritativeRecord());
  }

  refuse(command, reasonCode, reasonDetail, refusingActorOrSystemId = 'scar-authority') {
    const refusal = Object.freeze({
      schemaVersion: SCAR_VOXEL_SCHEMA_VERSION,
      worldId: this.worldId,
      commandId: command.commandId,
      refusalId: 'refusal-' + String(this.refusals.length + 1).padStart(6, '0'),
      refusingActorOrSystemId,
      reasonCode,
      reasonDetail,
      accessibilityText: rejectionText(reasonCode, reasonDetail),
      targetIds: [...command.targetChunkKeys],
      observedChunkRevisions: sortedObject(command.targetChunkKeys.map((key) => [
        key, this.chunks.get(key)?.revision ?? null,
      ])),
      requiredState: {},
      simulationTick: command.simulationTick,
      causalParentEventIds: [...command.causalParentEventIds],
    });
    this.refusals.push(refusal);
    const result = Object.freeze({ accepted: false, refusal });
    this.commandResults.set(command.commandId, result);
    return result;
  }

  submit(rawCommand) {
    let command;
    try {
      command = normalizeCommand(rawCommand);
    } catch (error) {
      const safe = {
        commandId: String(rawCommand?.commandId || 'invalid-' + (this.refusals.length + 1)),
        targetChunkKeys: [],
        causalParentEventIds: [],
        simulationTick: Number.isSafeInteger(rawCommand?.simulationTick) ? rawCommand.simulationTick : 0,
      };
      return this.refuse(safe, RefusalReason.INVALID_COMMAND, error.message);
    }
    if (this.commandResults.has(command.commandId)) return this.commandResults.get(command.commandId);
    if (command.schemaVersion !== SCAR_VOXEL_SCHEMA_VERSION) {
      return this.refuse(command, RefusalReason.SCHEMA_UNSUPPORTED,
        'Unsupported schema ' + command.schemaVersion + '; expected ' + SCAR_VOXEL_SCHEMA_VERSION + '.');
    }
    if (command.worldId !== this.worldId) {
      return this.refuse(command, RefusalReason.AUTHORITY_DENIED, 'Command belongs to another world lineage.');
    }
    for (const key of command.targetChunkKeys) {
      const chunk = this.chunks.get(key);
      if (!chunk) return this.refuse(command, RefusalReason.OUT_OF_RANGE, 'Unknown target chunk ' + key + '.');
      if (chunk.revision !== command.expectedChunkRevisions[key]) {
        return this.refuse(command, RefusalReason.STALE_REVISION,
          'Expected ' + key + ' revision ' + command.expectedChunkRevisions[key]
          + ', observed ' + chunk.revision + '.');
      }
    }
    if (command.parameters.momoRefuses === true) {
      const alternateRoute = String(command.parameters.alternateRoute || 'momo-route');
      return this.refuse(command, RefusalReason.ACTOR_REFUSED,
        'Momo-chan refused this route and chose ' + alternateRoute + '.', 'momo-chan');
    }
    if (command.parameters.blocked === true) {
      return this.refuse(command, RefusalReason.MATERIAL_BLOCKED,
        'The cut is blocked by authoritative material state.');
    }
    const surface = command.parameters.narrativeSurface ?? NarrativeSurface.GAME_ONLY;
    if (!Object.values(NarrativeSurface).includes(surface)) {
      return this.refuse(command, RefusalReason.AUTHORITY_DENIED,
        'Runtime action requested forbidden narrative surface ' + surface + '.');
    }
    if (command.operation !== 'MOVE_MATERIAL') {
      return this.refuse(command, RefusalReason.INVALID_COMMAND,
        'Bridge v0.1 accepts MOVE_MATERIAL only.');
    }
    return this.applyMoveMaterial(command, surface);
  }

  applyMoveMaterial(command, narrativeSurface) {
    let removals;
    let additions;
    try {
      removals = (command.parameters.removals ?? []).map((cell, index) => normalizeCell('removals[' + index + ']', cell));
      additions = (command.parameters.additions ?? []).map((cell, index) => normalizeCell('additions[' + index + ']', cell));
    } catch (error) {
      return this.refuse(command, RefusalReason.INVALID_COMMAND, error.message);
    }
    if (removals.length === 0 || additions.length === 0) {
      return this.refuse(command, RefusalReason.INVALID_COMMAND,
        'MOVE_MATERIAL requires at least one removal and one addition.');
    }
    const allCells = [...removals, ...additions];
    const touched = [...new Set(allCells.map((cell) => cell.chunkKey))].sort();
    if (canonicalJson(touched) !== canonicalJson(command.targetChunkKeys)) {
      return this.refuse(command, RefusalReason.INVALID_COMMAND,
        'targetChunkKeys must exactly match the chunks changed by the command.');
    }
    const occupiedKeys = new Set();
    const removedByMaterial = new Map();
    const addedByMaterial = new Map();
    for (const cell of removals) {
      if (occupiedKeys.has(cellKey(cell))) {
        return this.refuse(command, RefusalReason.INVALID_COMMAND, 'A source cell was named more than once.');
      }
      occupiedKeys.add(cellKey(cell));
      const chunk = this.chunks.get(cell.chunkKey);
      if (!chunk || !inBounds(chunk, cell.x, cell.y, cell.z)) {
        return this.refuse(command, RefusalReason.OUT_OF_RANGE,
          'A named source cell is outside its authoritative chunk.');
      }
      if (getMaterial(chunk, cell.x, cell.y, cell.z) !== cell.material) {
        return this.refuse(command, RefusalReason.MATERIAL_BLOCKED,
          'A named source cell does not contain the declared material.');
      }
      removedByMaterial.set(cell.material, (removedByMaterial.get(cell.material) ?? 0) + 1);
    }
    for (const cell of additions) {
      if (occupiedKeys.has(cellKey(cell))) {
        return this.refuse(command, RefusalReason.INVALID_COMMAND,
          'One cell cannot be both source and destination in the same shovel stroke.');
      }
      occupiedKeys.add(cellKey(cell));
      const chunk = this.chunks.get(cell.chunkKey);
      if (!chunk || !inBounds(chunk, cell.x, cell.y, cell.z)) {
        return this.refuse(command, RefusalReason.OUT_OF_RANGE,
          'A named spoil destination is outside its authoritative chunk.');
      }
      if (getMaterial(chunk, cell.x, cell.y, cell.z) !== 0) {
        return this.refuse(command, RefusalReason.MATERIAL_BLOCKED,
          'A named spoil destination is not empty.');
      }
      addedByMaterial.set(cell.material, (addedByMaterial.get(cell.material) ?? 0) + 1);
    }
    if (canonicalJson(sortedObject(removedByMaterial)) !== canonicalJson(sortedObject(addedByMaterial))) {
      return this.refuse(command, RefusalReason.MATERIAL_NOT_CONSERVED,
        'Removed and added cell counts differ by material.');
    }

    const editsByChunk = new Map(command.targetChunkKeys.map((key) => [key, []]));
    for (const cell of removals) editsByChunk.get(cell.chunkKey).push({ ...cell, material: 0 });
    for (const cell of additions) editsByChunk.get(cell.chunkKey).push({ ...cell });
    const edits = [...editsByChunk].map(([chunkKey, writes]) => ({
      chunkKey,
      writes: writes.map(({ x, y, z, material }) => ({ x, y, z, material })),
    }));
    const before = sortedObject(command.targetChunkKeys.map((key) => [key, this.chunks.get(key).revision]));
    const projectedAfter = Object.fromEntries(command.targetChunkKeys.map((key) => [key, before[key] + 1]));
    const ordinal = this.events.length + 1;
    const transactionId = 'tx-' + String(ordinal).padStart(6, '0');
    const eventId = 'event-' + String(ordinal).padStart(6, '0');
    const scarId = 'scar-' + String(this.scars.size + 1).padStart(6, '0');
    const materialLedger = sortedObject([...removedByMaterial].map(([material, quantity]) => [
      String(material), { removed: quantity, added: quantity, lost: 0 },
    ]));
    const payload = {
      operation: 'MOVE_MATERIAL',
      removals: [...removals].sort(compareCells),
      additions: [...additions].sort(compareCells),
      declaredIntent: command.declaredIntent,
      accessibilityInputSource: command.accessibilityInputSource,
      narrativeSurface,
    };
    const eventCore = {
      schemaVersion: SCAR_VOXEL_SCHEMA_VERSION,
      rulesetVersion: RULESET_VERSION,
      worldId: this.worldId,
      eventId,
      transactionId,
      sequenceInTransaction: 0,
      commandId: command.commandId,
      eventType: 'MATERIAL_MOVED',
      actorId: command.effectiveActorId,
      initiatorActorId: command.issuedByActorId,
      toolId: command.toolId,
      affectedChunkIds: [...command.targetChunkKeys],
      chunkRevisionBefore: before,
      chunkRevisionAfter: projectedAfter,
      materialLedger,
      scarIds: [scarId],
      causalParentEventIds: [...command.causalParentEventIds],
      simulationTick: command.simulationTick,
      deterministicSeed: null,
      payload,
      previousWorldEventHash: this.integrityHead,
    };
    const integrityHash = hashCanonical(eventCore);
    const event = Object.freeze({ ...eventCore, integrityHash });
    const scar = Object.freeze({
      scarId,
      worldId: this.worldId,
      scarType: String(command.parameters.scarType ?? 'EXCAVATION'),
      createdByEventId: eventId,
      lastModifiedByEventId: eventId,
      originatingActorId: command.effectiveActorId,
      initiatingActorId: command.issuedByActorId,
      toolId: command.toolId,
      affectedChunkIds: [...command.targetChunkKeys],
      materialLedger,
      narrativeSurface,
      createdTick: command.simulationTick,
      active: true,
    });

    // Exercise the donor carrier against private clones. No authoritative byte
    // changes until the full cross-chunk result and revisions are verified.
    const stagedChunks = new Map([...this.chunks].map(([key, chunk]) => [key, cloneChunk(chunk)]));
    const committed = applyAtomicChunkTransaction(
      stagedChunks,
      edits,
      command.expectedChunkRevisions,
    );
    if (!committed.accepted) {
      const reason = committed.reason === 'STALE_REVISION'
        ? RefusalReason.STALE_REVISION : RefusalReason.OUT_OF_RANGE;
      return this.refuse(command, reason, 'Voxel carrier refused staged writes: ' + committed.reason + '.');
    }
    const stagedAfter = sortedObject(committed.committed.map((item) => [item.chunkKey, item.revisionAfter]));
    if (canonicalJson(stagedAfter) !== canonicalJson(projectedAfter)) {
      return this.refuse(command, RefusalReason.INVALID_COMMAND,
        'Voxel carrier revision result diverged from the staged transaction.');
    }
    for (const key of command.targetChunkKeys) {
      const authoritative = this.chunks.get(key);
      const staged = stagedChunks.get(key);
      authoritative.materials = staged.materials;
      authoritative.revision = staged.revision;
    }
    this.events.push(event);
    this.scars.set(scarId, scar);
    this.integrityHead = integrityHash;
    const result = Object.freeze({ accepted: true, transactionId, events: [event], scarIds: [scarId] });
    this.commandResults.set(command.commandId, result);
    for (const key of command.targetChunkKeys) {
      for (const queue of this.presentationQueues) queue.mark(key, this.chunks.get(key).revision);
    }
    return result;
  }

  snapshot() {
    const authoritative = this.authoritativeRecord();
    return canonicalJson({
      snapshotSchemaVersion: SCAR_VOXEL_SCHEMA_VERSION,
      authoritative,
      authorityHash: hashCanonical(authoritative),
    });
  }

  static fromSnapshot(serialized) {
    const parsed = JSON.parse(serialized);
    if (parsed.snapshotSchemaVersion !== SCAR_VOXEL_SCHEMA_VERSION) {
      throw new Error('unsupported snapshot schema');
    }
    if (hashCanonical(parsed.authoritative) !== parsed.authorityHash) {
      throw new Error('authoritative snapshot verification failed');
    }
    const data = parsed.authoritative;
    const authority = new ScarVoxelAuthority(data.worldId);
    for (const record of Object.values(data.chunks)) {
      authority.addChunk(createVoxelChunk({
        chunkId: record.chunkId,
        sizeX: record.sizeX,
        sizeY: record.sizeY,
        sizeZ: record.sizeZ,
        cellSizeFixed: record.cellSizeFixed,
        originFixed: record.originFixed,
        materials: record.materials,
        revision: record.revision,
      }));
    }
    authority.events = data.events;
    authority.refusals = data.refusals;
    authority.scars = new Map(Object.entries(data.scars));
    authority.commandResults = new Map(Object.entries(data.commandResults));
    authority.integrityHead = data.integrityHead;
    if (authority.authorityHash() !== parsed.authorityHash) {
      throw new Error('loaded authority diverged from snapshot');
    }
    return authority;
  }

  static replayGenesis(genesisChunks, events) {
    if (!Array.isArray(genesisChunks) || genesisChunks.length === 0) {
      throw new TypeError('genesisChunks must be a non-empty array');
    }
    const authority = new ScarVoxelAuthority(genesisChunks[0].chunkId.worldId);
    genesisChunks.forEach((chunk) => authority.addChunk(chunk));
    for (const supplied of events) {
      if (supplied.previousWorldEventHash !== authority.integrityHead) {
        throw new Error('event hash chain is broken at ' + supplied.eventId);
      }
      const { integrityHash, ...core } = supplied;
      if (hashCanonical(core) !== integrityHash) throw new Error('event integrity failed at ' + supplied.eventId);
      const editsByChunk = new Map(supplied.affectedChunkIds.map((key) => [key, []]));
      for (const cell of supplied.payload.removals) {
        editsByChunk.get(cell.chunkKey).push({ x: cell.x, y: cell.y, z: cell.z, material: 0 });
      }
      for (const cell of supplied.payload.additions) {
        editsByChunk.get(cell.chunkKey).push({ x: cell.x, y: cell.y, z: cell.z, material: cell.material });
      }
      const committed = applyAtomicChunkTransaction(
        authority.chunks,
        [...editsByChunk].map(([chunkKey, writes]) => ({ chunkKey, writes })),
        supplied.chunkRevisionBefore,
      );
      if (!committed.accepted) throw new Error('replay mutation refused at ' + supplied.eventId);
      const observedAfter = sortedObject(committed.committed.map((item) => [item.chunkKey, item.revisionAfter]));
      if (canonicalJson(observedAfter) !== canonicalJson(supplied.chunkRevisionAfter)) {
        throw new Error('replay revision mismatch at ' + supplied.eventId);
      }
      authority.events.push(structuredClone(supplied));
      const scarId = supplied.scarIds[0];
      authority.scars.set(scarId, {
        scarId,
        worldId: supplied.worldId,
        scarType: 'EXCAVATION',
        createdByEventId: supplied.eventId,
        lastModifiedByEventId: supplied.eventId,
        originatingActorId: supplied.actorId,
        initiatingActorId: supplied.initiatorActorId,
        toolId: supplied.toolId,
        affectedChunkIds: supplied.affectedChunkIds,
        materialLedger: supplied.materialLedger,
        narrativeSurface: supplied.payload.narrativeSurface,
        createdTick: supplied.simulationTick,
        active: true,
      });
      const result = {
        accepted: true,
        transactionId: supplied.transactionId,
        events: [structuredClone(supplied)],
        scarIds: [scarId],
      };
      authority.commandResults.set(supplied.commandId, result);
      authority.integrityHead = supplied.integrityHash;
    }
    return authority;
  }
}

function makeFixtureWorld() {
  const a = createVoxelChunk({
    chunkId: { worldId: 'chapter-9', x: 0, y: 0, z: 0 },
    sizeX: 4, sizeY: 4, sizeZ: 4,
  });
  const b = createVoxelChunk({
    chunkId: { worldId: 'chapter-9', x: 1, y: 0, z: 0 },
    sizeX: 4, sizeY: 4, sizeZ: 4,
  });
  a.materials[cellIndex(a, 3, 1, 1)] = 7;
  a.materials[cellIndex(a, 2, 1, 1)] = 7;
  const authority = new ScarVoxelAuthority('chapter-9');
  authority.addChunk(a);
  authority.addChunk(b);
  return { authority, genesis: [a, b], aKey: a.key, bKey: b.key };
}

function makeShovelCommand(authority, aKey, bKey, commandId = 'shovel-001', overrides = {}) {
  return {
    schemaVersion: SCAR_VOXEL_SCHEMA_VERSION,
    worldId: 'chapter-9',
    commandId,
    issuedByActorId: 'drew',
    effectiveActorId: 'tetsuya',
    toolId: 'shovel-1',
    operation: 'MOVE_MATERIAL',
    targetChunkKeys: [aKey, bKey],
    expectedChunkRevisions: {
      [aKey]: authority.chunks.get(aKey).revision,
      [bKey]: authority.chunks.get(bKey).revision,
    },
    parameters: {
      removals: [{ chunkKey: aKey, x: 3, y: 1, z: 1, material: 7 }],
      additions: [{ chunkKey: bKey, x: 0, y: 1, z: 1, material: 7 }],
      scarType: 'EXCAVATION',
      narrativeSurface: NarrativeSurface.PLAYER_HISTORY,
      ...overrides,
    },
    simulationTick: 100,
    declaredIntent: 'drive, lift, and cast spoil across the boundary',
    causalParentEventIds: [],
    accessibilityInputSource: 'assistive-or-standard-equivalent',
  };
}

export function runScarVoxelAuthorityTests() {
  let passed = 0;
  const test = (name, fn) => {
    fn();
    passed += 1;
    return name;
  };

  test('atomic cross-chunk shovel and conservation', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    const result = authority.submit(makeShovelCommand(authority, aKey, bKey));
    assert.equal(result.accepted, true);
    assert.equal(authority.chunks.get(aKey).revision, 1);
    assert.equal(authority.chunks.get(bKey).revision, 1);
    assert.equal(getMaterial(authority.chunks.get(aKey), 3, 1, 1), 0);
    assert.equal(getMaterial(authority.chunks.get(bKey), 0, 1, 1), 7);
    assert.deepEqual(result.events[0].materialLedger['7'], { removed: 1, added: 1, lost: 0 });
  });

  test('refused transaction changes no cell or revision', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    const before = authority.authorityHash();
    const command = makeShovelCommand(authority, aKey, bKey, 'bad-destination', {
      additions: [{ chunkKey: bKey, x: 99, y: 1, z: 1, material: 7 }],
    });
    const result = authority.submit(command);
    assert.equal(result.accepted, false);
    assert.equal(result.refusal.reasonCode, RefusalReason.OUT_OF_RANGE);
    assert.equal(authority.events.length, 0);
    assert.equal(authority.chunks.get(aKey).revision, 0);
    assert.equal(getMaterial(authority.chunks.get(aKey), 3, 1, 1), 7);
    assert.notEqual(authority.authorityHash(), before, 'refusal itself must remain forensic evidence');
  });

  test('duplicate command is idempotent even after later work', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    const firstCommand = makeShovelCommand(authority, aKey, bKey, 'duplicate');
    const first = authority.submit(firstCommand);
    const secondCommand = makeShovelCommand(authority, aKey, bKey, 'later', {
      removals: [{ chunkKey: aKey, x: 2, y: 1, z: 1, material: 7 }],
      additions: [{ chunkKey: bKey, x: 1, y: 1, z: 1, material: 7 }],
    });
    authority.submit(secondCommand);
    assert.equal(authority.submit(firstCommand), first);
    assert.equal(authority.events.length, 2);
  });

  test('stale expected revision refuses before voxel staging', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    const stale = makeShovelCommand(authority, aKey, bKey, 'stale');
    authority.chunks.get(aKey).revision = 1;
    const result = authority.submit(stale);
    assert.equal(result.refusal.reasonCode, RefusalReason.STALE_REVISION);
    assert.match(result.refusal.accessibilityText, /Refresh/);
    assert.equal(authority.events.length, 0);
  });

  test('material mismatch is refused without creating dirt', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    const command = makeShovelCommand(authority, aKey, bKey, 'matter-lie', {
      additions: [
        { chunkKey: bKey, x: 0, y: 1, z: 1, material: 7 },
        { chunkKey: bKey, x: 1, y: 1, z: 1, material: 7 },
      ],
    });
    const result = authority.submit(command);
    assert.equal(result.refusal.reasonCode, RefusalReason.MATERIAL_NOT_CONSERVED);
    assert.equal(authority.chunks.get(bKey).materials.reduce((sum, value) => sum + value, 0), 0);
  });

  test('Momo-chan refusal remains hers and changes no terrain', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    const command = makeShovelCommand(authority, aKey, bKey, 'momo', {
      momoRefuses: true,
      alternateRoute: 'ridge-route',
    });
    const result = authority.submit(command);
    assert.equal(result.refusal.refusingActorOrSystemId, 'momo-chan');
    assert.match(result.refusal.accessibilityText, /ridge-route/);
    assert.equal(authority.events.length, 0);
  });

  test('novel-canon firewall runs before mutation', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    const command = makeShovelCommand(authority, aKey, bKey, 'canon-lie', {
      narrativeSurface: 'NOVEL_CANON',
    });
    const result = authority.submit(command);
    assert.equal(result.refusal.reasonCode, RefusalReason.AUTHORITY_DENIED);
    assert.equal(authority.chunks.get(aKey).revision, 0);
  });

  test('snapshot load preserves every authoritative byte', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    authority.submit(makeShovelCommand(authority, aKey, bKey));
    const loaded = ScarVoxelAuthority.fromSnapshot(authority.snapshot());
    assert.equal(loaded.authorityHash(), authority.authorityHash());
    assert.equal(loaded.snapshot(), authority.snapshot());
  });

  test('snapshot tampering fails closed', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    authority.submit(makeShovelCommand(authority, aKey, bKey));
    const parsed = JSON.parse(authority.snapshot());
    parsed.authoritative.chunks[aKey].materials[cellIndex(authority.chunks.get(aKey), 0, 0, 0)] = 99;
    assert.throws(() => ScarVoxelAuthority.fromSnapshot(JSON.stringify(parsed)), /verification failed/);
  });

  test('replay is deterministic and rejects broken lineage', () => {
    const { authority, genesis, aKey, bKey } = makeFixtureWorld();
    authority.submit(makeShovelCommand(authority, aKey, bKey));
    const first = ScarVoxelAuthority.replayGenesis(genesis, authority.events);
    const second = ScarVoxelAuthority.replayGenesis(genesis, authority.events);
    assert.equal(first.authorityHash(), second.authorityHash());
    const broken = structuredClone(authority.events);
    broken[0].previousWorldEventHash = 'COUNTERFEIT';
    assert.throws(() => ScarVoxelAuthority.replayGenesis(genesis, broken), /hash chain is broken/);
  });

  test('remesh queue issues at most one job per frame and rejects stale work', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    const queue = authority.createPresentationQueue('tim-phone-low');
    authority.submit(makeShovelCommand(authority, aKey, bKey, 'first'));
    queue.beginFrame();
    const oldJob = queue.issueOne();
    assert.ok(oldJob);
    assert.equal(queue.issueOne(), null);
    const second = makeShovelCommand(authority, aKey, bKey, 'second', {
      removals: [{ chunkKey: aKey, x: 2, y: 1, z: 1, material: 7 }],
      additions: [{ chunkKey: bKey, x: 1, y: 1, z: 1, material: 7 }],
    });
    authority.submit(second);
    assert.equal(queue.acceptResult(oldJob), false);
    queue.beginFrame();
    const currentJob = queue.issueOne();
    assert.equal(currentJob.sourceRevision, 2);
    assert.equal(queue.acceptResult(currentJob), true);
  });

  test('renderer profiles cannot alter gameplay authority', () => {
    const { authority, aKey, bKey } = makeFixtureWorld();
    const low = authority.createPresentationQueue('tim-phone-low');
    const high = authority.createPresentationQueue('high-quality');
    authority.submit(makeShovelCommand(authority, aKey, bKey));
    const before = authority.authorityHash();
    low.beginFrame(); high.beginFrame();
    assert.equal(low.acceptResult(low.issueOne()), true);
    assert.equal(high.acceptResult(high.issueOne()), true);
    assert.equal(authority.authorityHash(), before);
  });

  return {
    passed,
    authorityFixtures: 12,
    boundedRemeshJobsPerFrame: 1,
    finalLaw: 'the shovel may cut earth; presentation may not rewrite it',
  };
}

if (process.argv[1]?.endsWith('scar_voxel_authority_v0_1.mjs')) {
  console.log(JSON.stringify(runScarVoxelAuthorityTests()));
}

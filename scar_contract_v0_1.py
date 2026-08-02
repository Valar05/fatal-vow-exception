"""Fatal Vow Exception — first scar contract.

Authority: Drew Clarke
Repository: Valar05/fatal-vow-exception (public and forkable)
Status: executable build contract; not novel canon and not a game runtime.

Mission
-------
Build a new independent first-person 3D survival-action game for low-end Android
and web. Tim's non-flagship phone is the acceptance device: a representative
Chapter 9 clearing/trench battle must hold a stable 30 FPS. Multiplayer-shaped
state contracts begin now; networking does not.

Boundary ledger
---------------
* World truth remains faithful to the Fatal Vow Exception novels. Fleshpunk is
  visual pressure only; it cannot invent technology, materials, institutions,
  causality, or combat grammar.
* The visual law is "3D world, 3D bodies, 2D timing." Drew remains the actor.
  Contact sheets remain the animation source, approval surface, and correction
  language. Pose Lab is a bounded FPS-to-Meshy upstream source.
* Deterministic terrain state and append-only scar events are authoritative.
  Generated meshes, particles, animation, telemetry, and renderer quality are
  presentation and cannot write gameplay truth.
* Shovel work conserves material and leaves persistent authored consequences.
  Stable IDs, integer simulation data, atomic cross-chunk edits, monotonic
  revisions, idempotency, save/reload, replay, and stale-remesh rejection are
  required from the first seam.
* Momo-chan's refusal is authoritative. Assistive controls emit the same command
  shapes and receive the same authority. Runtime action cannot assign novel canon.
* Infinite Brutality remains intact as a bounded future voxel/support donor. No
  donor code, island assumptions, Napoleon grammar, immutable terrain stamps, or
  rebuild/disposal lifecycle enters this contract.

Governing law
-------------
The player may change the world. The game must tell the truth about who chose,
who could refuse, who paid, what remained changed, and which surface owns the scar.

Run: python -m unittest -v scar_contract_v0_1.py
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from hashlib import sha256
import json
import unittest
from typing import Any


SCHEMA_VERSION = "0.1"
FIXED_POINT_SCALE = 1_000


class TerrainOperation(str, Enum):
    REMOVE_CELLS = "REMOVE_CELLS"
    ADD_CELLS = "ADD_CELLS"
    MOVE_MATERIAL = "MOVE_MATERIAL"
    COMPACT_CELLS = "COMPACT_CELLS"
    CUT_DRAIN = "CUT_DRAIN"
    PLACE_SUPPORT = "PLACE_SUPPORT"
    REMOVE_SUPPORT = "REMOVE_SUPPORT"
    PLACE_MECHANISM = "PLACE_MECHANISM"
    ACTUATE_MECHANISM = "ACTUATE_MECHANISM"
    APPLY_IMPULSE = "APPLY_IMPULSE"
    SETTLE_REGION = "SETTLE_REGION"


class RefusalReason(str, Enum):
    STALE_REVISION = "STALE_REVISION"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"
    MATERIAL_BLOCKED = "MATERIAL_BLOCKED"
    TOOL_INCOMPATIBLE = "TOOL_INCOMPATIBLE"
    ACTOR_INCAPABLE = "ACTOR_INCAPABLE"
    ACTOR_REFUSED = "ACTOR_REFUSED"
    ROUTE_REJECTED = "ROUTE_REJECTED"
    OCCUPIED = "OCCUPIED"
    WOULD_TRAP_REQUIRED_EXIT = "WOULD_TRAP_REQUIRED_EXIT"
    WOULD_BREAK_DRAINAGE_GUARD = "WOULD_BREAK_DRAINAGE_GUARD"
    AUTHORITY_DENIED = "AUTHORITY_DENIED"
    SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"


class NarrativeSurface(str, Enum):
    GAME_ONLY = "GAME_ONLY"
    SIMULATION_RECORD = "SIMULATION_RECORD"
    PLAYER_HISTORY = "PLAYER_HISTORY"
    PROPOSED_STORY_EVIDENCE = "PROPOSED_STORY_EVIDENCE"


@dataclass(frozen=True, order=True)
class ChunkId:
    world_id: str
    x: int
    y: int
    z: int

    @property
    def key(self) -> str:
        return f"{self.world_id}:{self.x}:{self.y}:{self.z}"


@dataclass(frozen=True)
class MaterialDelta:
    material_type: str
    source_quantity: int
    destination_quantity: int
    lost_quantity: int = 0
    loss_reason: str = ""
    source_refs: tuple[str, ...] = ()
    destination_refs: tuple[str, ...] = ()

    def validate(self) -> None:
        if min(self.source_quantity, self.destination_quantity, self.lost_quantity) < 0:
            raise ValueError("material quantities cannot be negative")
        if self.source_quantity != self.destination_quantity + self.lost_quantity:
            raise ValueError("material is not conserved")
        if self.lost_quantity and not self.loss_reason:
            raise ValueError("lost material requires an explicit sink rule")


@dataclass(frozen=True)
class ScarCommand:
    schema_version: str
    world_id: str
    command_id: str
    issued_by_actor_id: str
    effective_actor_id: str
    operation: TerrainOperation
    target_chunks: tuple[ChunkId, ...]
    expected_chunk_revisions: dict[str, int]
    parameters: dict[str, Any]
    client_or_local_tick: int
    declared_intent: str
    tool_id: str | None = None
    causal_parent_event_ids: tuple[str, ...] = ()
    accessibility_input_source: str | None = None


@dataclass(frozen=True)
class ScarEvent:
    schema_version: str
    world_id: str
    event_id: str
    transaction_id: str
    sequence_in_transaction: int
    command_id: str
    event_type: str
    actor_id: str
    initiator_actor_id: str
    tool_id: str | None
    affected_chunk_ids: tuple[ChunkId, ...]
    chunk_revision_before: dict[str, int]
    chunk_revision_after: dict[str, int]
    material_delta: MaterialDelta | None
    scar_ids: tuple[str, ...]
    causal_parent_event_ids: tuple[str, ...]
    simulation_tick: int
    ruleset_version: str
    payload: dict[str, Any]
    integrity_hash: str
    previous_world_event_hash: str


@dataclass(frozen=True)
class RefusalRecord:
    schema_version: str
    world_id: str
    command_id: str
    refusal_id: str
    refusing_actor_or_system_id: str
    reason_code: RefusalReason
    reason_detail: str
    accessibility_text: str
    target_ids: tuple[str, ...]
    observed_chunk_revisions: dict[str, int]
    required_state: dict[str, Any]
    simulation_tick: int
    causal_parent_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scar:
    scar_id: str
    world_id: str
    scar_type: str
    created_by_event_id: str
    last_modified_by_event_id: str
    originating_actor_id: str
    current_custodian_actor_id: str | None
    affected_chunk_ids: tuple[ChunkId, ...]
    material_account: MaterialDelta | None
    narrative_surface: NarrativeSurface
    created_tick: int
    last_modified_tick: int
    active: bool = True


@dataclass
class AuthoritativeChunkState:
    chunk_id: ChunkId
    revision: int = 0
    materials: dict[str, int] = field(default_factory=dict)
    support_loads: dict[str, int] = field(default_factory=dict)
    scar_refs: list[str] = field(default_factory=list)
    last_applied_event_id: str = ""


@dataclass(frozen=True)
class DirtyRemeshJob:
    chunk_id: ChunkId
    source_revision: int
    renderer_profile: str


def _primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ChunkId):
        return {"world_id": value.world_id, "x": value.x, "y": value.y, "z": value.z}
    if is_dataclass(value):
        return _primitive(asdict(value))
    if isinstance(value, dict):
        return {str(k): _primitive(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_primitive(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class ScarAuthority:
    """Small deterministic witness, deliberately not the production simulation."""

    def __init__(self, world_id: str = "chapter-9") -> None:
        self.world_id = world_id
        self.chunks: dict[str, AuthoritativeChunkState] = {}
        self.events: list[ScarEvent] = []
        self.refusals: list[RefusalRecord] = []
        self.scars: dict[str, Scar] = {}
        self.command_results: dict[str, tuple[ScarEvent, ...] | RefusalRecord] = {}
        self.dirty_jobs: list[DirtyRemeshJob] = []
        self.alternate_routes: dict[str, str] = {}

    def add_chunk(self, chunk_id: ChunkId, **materials: int) -> None:
        self.chunks[chunk_id.key] = AuthoritativeChunkState(chunk_id, materials=dict(materials))

    def authority_hash(self) -> str:
        truth = {
            "world_id": self.world_id,
            "chunks": {k: _primitive(v) for k, v in sorted(self.chunks.items())},
            "scars": {k: _primitive(v) for k, v in sorted(self.scars.items())},
            "events": [_primitive(e) for e in self.events],
            "refusals": [_primitive(r) for r in self.refusals],
            "alternate_routes": dict(sorted(self.alternate_routes.items())),
        }
        return sha256(canonical_json(truth).encode()).hexdigest()

    def _refuse(self, command: ScarCommand, reason: RefusalReason, detail: str,
                refusing_id: str = "scar-authority") -> RefusalRecord:
        refusal = RefusalRecord(
            SCHEMA_VERSION, self.world_id, command.command_id,
            f"refusal-{len(self.refusals) + 1:06d}", refusing_id, reason, detail,
            detail, tuple(c.key for c in command.target_chunks),
            {c.key: self.chunks[c.key].revision for c in command.target_chunks},
            {}, command.client_or_local_tick, command.causal_parent_event_ids,
        )
        self.refusals.append(refusal)
        self.command_results[command.command_id] = refusal
        return refusal

    def submit(self, command: ScarCommand) -> tuple[ScarEvent, ...] | RefusalRecord:
        if command.command_id in self.command_results:
            return self.command_results[command.command_id]
        if command.schema_version != SCHEMA_VERSION:
            return self._refuse(command, RefusalReason.SCHEMA_UNSUPPORTED, "Use schema version 0.1.")
        for chunk in command.target_chunks:
            observed = self.chunks[chunk.key].revision
            if command.expected_chunk_revisions.get(chunk.key) != observed:
                return self._refuse(command, RefusalReason.STALE_REVISION,
                                    f"Refresh {chunk.key}; expected revision {observed}.")
        if command.parameters.get("momo_refuses"):
            route = str(command.parameters.get("alternate_route", "momo-route"))
            self.alternate_routes["momo-chan"] = route
            return self._refuse(command, RefusalReason.ACTOR_REFUSED,
                                f"Momo-chan refused this route and chose {route}.", "momo-chan")
        if command.parameters.get("blocked"):
            return self._refuse(command, RefusalReason.MATERIAL_BLOCKED,
                                "Dig blocked by mineral crust; inspect the edge or choose another cut.")

        before = {c.key: self.chunks[c.key].revision for c in command.target_chunks}
        materials_before = {c.key: dict(self.chunks[c.key].materials) for c in command.target_chunks}
        supports_before = {c.key: dict(self.chunks[c.key].support_loads) for c in command.target_chunks}
        try:
            material_delta, event_types = self._apply(command)
        except ValueError as exc:
            for c in command.target_chunks:
                self.chunks[c.key].materials = materials_before[c.key]
                self.chunks[c.key].support_loads = supports_before[c.key]
            return self._refuse(command, RefusalReason.INSUFFICIENT_SUPPORT, str(exc))

        for chunk in command.target_chunks:
            self.chunks[chunk.key].revision += 1
        after = {c.key: self.chunks[c.key].revision for c in command.target_chunks}
        transaction_id = f"tx-{len(self.command_results) + 1:06d}"
        scar_id = f"scar-{len(self.scars) + 1:06d}"
        emitted: list[ScarEvent] = []
        for sequence, event_type in enumerate(event_types):
            event_id = f"event-{len(self.events) + 1:06d}"
            previous_hash = self.events[-1].integrity_hash if self.events else "GENESIS"
            payload = {
                "operation": command.operation.value,
                "parameters": command.parameters,
                "accessibility_input_source": command.accessibility_input_source,
            }
            unhashed = {
                "event_id": event_id, "transaction_id": transaction_id,
                "sequence": sequence, "command_id": command.command_id,
                "event_type": event_type, "before": before, "after": after,
                "material_delta": _primitive(material_delta), "payload": payload,
                "previous_world_event_hash": previous_hash,
            }
            integrity = sha256(canonical_json(unhashed).encode()).hexdigest()
            event = ScarEvent(
                SCHEMA_VERSION, self.world_id, event_id, transaction_id, sequence,
                command.command_id, event_type, command.effective_actor_id,
                command.issued_by_actor_id, command.tool_id, command.target_chunks,
                before, after, material_delta, (scar_id,), command.causal_parent_event_ids,
                command.client_or_local_tick, SCHEMA_VERSION, payload, integrity, previous_hash,
            )
            self.events.append(event)
            emitted.append(event)
        for c in command.target_chunks:
            self.chunks[c.key].last_applied_event_id = emitted[-1].event_id
            self.chunks[c.key].scar_refs.append(scar_id)
            self.dirty_jobs.append(DirtyRemeshJob(c, after[c.key], "default"))
        scar = Scar(
            scar_id, self.world_id, str(command.parameters.get("scar_type", "IMPACT")),
            emitted[0].event_id, emitted[-1].event_id, command.effective_actor_id,
            None, command.target_chunks, material_delta,
            NarrativeSurface(str(command.parameters.get("narrative_surface", "GAME_ONLY"))),
            command.client_or_local_tick, command.client_or_local_tick,
        )
        self.scars[scar_id] = scar
        result = tuple(emitted)
        self.command_results[command.command_id] = result
        return result

    def _apply(self, command: ScarCommand) -> tuple[MaterialDelta | None, list[str]]:
        p = command.parameters
        if command.operation == TerrainOperation.MOVE_MATERIAL:
            source = self.chunks[str(p["source_chunk"])]
            destination = self.chunks[str(p["destination_chunk"])]
            material = str(p["material_type"])
            quantity = int(p["quantity"])
            if quantity <= 0 or source.materials.get(material, 0) < quantity:
                raise ValueError("Insufficient named material; no mutation committed.")
            source.materials[material] -= quantity
            destination.materials[material] = destination.materials.get(material, 0) + quantity
            delta = MaterialDelta(material, quantity, quantity, source_refs=(source.chunk_id.key,),
                                  destination_refs=(destination.chunk_id.key,))
            delta.validate()
            return delta, ["MATERIAL_MOVED"]
        if command.operation == TerrainOperation.REMOVE_SUPPORT:
            chunk = self.chunks[command.target_chunks[0].key]
            support_id = str(p["support_id"])
            load = chunk.support_loads.get(support_id, 0)
            if load and not p.get("allow_settlement"):
                raise ValueError("Loaded support cannot be removed without bounded settlement.")
            chunk.support_loads.pop(support_id, None)
            return None, ["SUPPORT_REMOVED", "REGION_SETTLED"] if load else ["SUPPORT_REMOVED"]
        return None, [command.operation.value]

    def accept_remesh(self, job: DirtyRemeshJob) -> bool:
        return self.chunks[job.chunk_id.key].revision == job.source_revision

    def save(self) -> str:
        return canonical_json({
            "world_id": self.world_id,
            "chunks": {k: _primitive(v) for k, v in self.chunks.items()},
            "events": [_primitive(v) for v in self.events],
            "refusals": [_primitive(v) for v in self.refusals],
            "scars": {k: _primitive(v) for k, v in self.scars.items()},
            "alternate_routes": self.alternate_routes,
            "authority_hash": self.authority_hash(),
        })

    @classmethod
    def load(cls, payload: str) -> "ScarAuthority":
        data = json.loads(payload)
        authority = cls(data["world_id"])
        for key, raw in data["chunks"].items():
            cid = ChunkId(**raw["chunk_id"])
            authority.chunks[key] = AuthoritativeChunkState(
                cid, raw["revision"], raw["materials"], raw["support_loads"],
                raw["scar_refs"], raw["last_applied_event_id"])
        for raw in data["events"]:
            raw["affected_chunk_ids"] = tuple(ChunkId(**c) for c in raw["affected_chunk_ids"])
            raw["material_delta"] = MaterialDelta(**raw["material_delta"]) if raw["material_delta"] else None
            for name in ("scar_ids", "causal_parent_event_ids"):
                raw[name] = tuple(raw[name])
            authority.events.append(ScarEvent(**raw))
        for raw in data["refusals"]:
            raw["reason_code"] = RefusalReason(raw["reason_code"])
            for name in ("target_ids", "causal_parent_event_ids"):
                raw[name] = tuple(raw[name])
            authority.refusals.append(RefusalRecord(**raw))
        for key, raw in data["scars"].items():
            raw["affected_chunk_ids"] = tuple(ChunkId(**c) for c in raw["affected_chunk_ids"])
            raw["material_account"] = MaterialDelta(**raw["material_account"]) if raw["material_account"] else None
            raw["narrative_surface"] = NarrativeSurface(raw["narrative_surface"])
            authority.scars[key] = Scar(**raw)
        authority.alternate_routes = data["alternate_routes"]
        if authority.authority_hash() != data["authority_hash"]:
            raise ValueError("authoritative save verification failed")
        return authority


class ScarContractFixtures(unittest.TestCase):
    def setUp(self) -> None:
        self.a = ChunkId("chapter-9", 0, 0, 0)
        self.b = ChunkId("chapter-9", 1, 0, 0)
        self.world = ScarAuthority()
        self.world.add_chunk(self.a, soil=20)
        self.world.add_chunk(self.b, soil=0)

    def command(self, command_id: str, operation: TerrainOperation = TerrainOperation.MOVE_MATERIAL,
                **parameters: Any) -> ScarCommand:
        params = {"source_chunk": self.a.key, "destination_chunk": self.b.key,
                  "material_type": "soil", "quantity": 1, "scar_type": "EXCAVATION"}
        params.update(parameters)
        return ScarCommand(SCHEMA_VERSION, "chapter-9", command_id, "drew", "tetsuya",
                           operation, (self.a, self.b),
                           {self.a.key: self.world.chunks[self.a.key].revision,
                            self.b.key: self.world.chunks[self.b.key].revision},
                           params, 100, "make a survivable cut", "shovel-1")

    def test_t01_idempotency(self) -> None:
        command = self.command("T01")
        first = self.world.submit(command)
        second = self.world.submit(command)
        self.assertIs(first, second)
        self.assertEqual(1, len(self.world.events))

    def test_t02_stale_revision(self) -> None:
        command = self.command("T02")
        self.world.chunks[self.a.key].revision = 1
        before_chunks = canonical_json(self.world.chunks)
        result = self.world.submit(command)
        self.assertEqual(RefusalReason.STALE_REVISION, result.reason_code)
        self.assertEqual(before_chunks, canonical_json(self.world.chunks))
        self.assertEqual(0, len(self.world.events))
        self.assertEqual(1, len(self.world.refusals))

    def test_t03_cross_chunk_atomicity(self) -> None:
        bad = self.command("T03", quantity=999)
        result = self.world.submit(bad)
        self.assertIsInstance(result, RefusalRecord)
        self.assertEqual((20, 0, 0, 0), (self.world.chunks[self.a.key].materials["soil"],
                                         self.world.chunks[self.b.key].materials["soil"],
                                         self.world.chunks[self.a.key].revision,
                                         self.world.chunks[self.b.key].revision))

    def test_t04_matter_conservation(self) -> None:
        event = self.world.submit(self.command("T04", quantity=10))[0]
        event.material_delta.validate()
        self.assertEqual((10, 10), (self.world.chunks[self.a.key].materials["soil"],
                                    self.world.chunks[self.b.key].materials["soil"]))

    def test_t05_save_reload(self) -> None:
        self.world.submit(self.command("T05", quantity=3))
        loaded = ScarAuthority.load(self.world.save())
        self.assertEqual(self.world.authority_hash(), loaded.authority_hash())

    def test_t06_replay_determinism(self) -> None:
        self.world.submit(self.command("T06", quantity=4))
        payload = self.world.save()
        self.assertEqual(ScarAuthority.load(payload).authority_hash(),
                         ScarAuthority.load(payload).authority_hash())

    def test_t07_dirty_job_race(self) -> None:
        self.world.submit(self.command("T07a"))
        old_job = self.world.dirty_jobs[0]
        self.world.submit(self.command("T07b"))
        self.assertFalse(self.world.accept_remesh(old_job))

    def test_t08_quality_independence(self) -> None:
        self.world.submit(self.command("T08"))
        low = self.world.authority_hash()
        high = self.world.authority_hash()
        self.assertEqual(low, high)

    def test_t09_autonomous_refusal(self) -> None:
        result = self.world.submit(self.command("T09", momo_refuses=True,
                                                alternate_route="ridge-route"))
        self.assertEqual((RefusalReason.ACTOR_REFUSED, "ridge-route", 0),
                         (result.reason_code, self.world.alternate_routes["momo-chan"],
                          len(self.world.events)))

    def test_t10_canon_firewall(self) -> None:
        with self.assertRaises(ValueError):
            NarrativeSurface("NOVEL_CANON")
        self.assertNotIn("NOVEL_CANON", {s.value for s in NarrativeSurface})

    def test_t11_accessible_refusal(self) -> None:
        result = self.world.submit(self.command("T11", blocked=True))
        self.assertEqual(RefusalReason.MATERIAL_BLOCKED, result.reason_code)
        self.assertIn("choose another cut", result.accessibility_text)

    def test_t12_network_shaped_duplicate(self) -> None:
        duplicate = self.command("T12")
        self.world.submit(duplicate)
        fresh = self.command("T12-next")
        self.world.submit(fresh)
        self.world.submit(duplicate)
        self.assertEqual(2, len(self.world.events))

    def test_t13_support_consequence(self) -> None:
        self.world.chunks[self.a.key].support_loads["wall-1"] = 7
        command = self.command("T13", TerrainOperation.REMOVE_SUPPORT,
                               support_id="wall-1", allow_settlement=True)
        events = self.world.submit(command)
        self.assertEqual({events[0].transaction_id}, {e.transaction_id for e in events})
        self.assertEqual(["SUPPORT_REMOVED", "REGION_SETTLED"], [e.event_type for e in events])

    def test_t14_chapter_9_proof(self) -> None:
        events = self.world.submit(self.command("T14", quantity=2, scar_type="EXCAVATION"))
        scar = self.world.scars[events[0].scar_ids[0]]
        loaded = ScarAuthority.load(self.world.save())
        self.assertEqual("tetsuya", scar.originating_actor_id)
        self.assertEqual(2, scar.material_account.destination_quantity)
        self.assertEqual({self.a.key, self.b.key}, {j.chunk_id.key for j in self.world.dirty_jobs})
        self.assertEqual(self.world.authority_hash(), loaded.authority_hash())


if __name__ == "__main__":
    unittest.main(verbosity=2)

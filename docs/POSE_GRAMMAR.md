# Fatal Vow Pose Grammar

Status: architecture adopted; mined catalog is candidate evidence
Authority: Drew Clarke
Date: 2026-08-02

## Decision

Do not build animation clips as isolated finished objects. Mine useful source-exact poses, classify them, and compose performances from a shared grammar.

An animation is a **score over pose recipes**. A song is also a score over pose recipes. Gameplay, cinematics, music, and authored demonstrations use the same vocabulary while retaining different timing and interruption rules.

## Compostable units

1. **Pose atom** — one source-exact skeletal state with provenance.
2. **Contact atom** — a declared relationship such as hand-to-handle, foot-to-ground, palm-to-wall, or body-to-prop.
3. **Layer atom** — rear hand/forearm, weapon, and foreground fingers/knuckles registered to the established FPS camera.
4. **Transition** — an allowed path between compatible atoms, including the constraints that must remain locked.
5. **Score event** — cue, accent, hold, release, repeat, interrupt, transition, or stop in seconds, beats, bars, or named markers.
6. **Pose recipe** — donor atoms plus joint subsets, explicit overrides, contacts, sockets, occlusion, camera, and acceptance status.

A rejected animation may still yield accepted atoms, constraints, transitions, or failure evidence. Nothing useful has to die merely because the sentence failed.

## Three truths, kept separate

- **Motion truth:** source transforms from `motion_corpus.json`.
- **Image truth:** accepted hand identity, weapon geometry, camera, silhouettes, and layer occlusion.
- **Timing truth:** the score that chooses when a pose changes or holds.

The runtime stack is:

1. rear hand/palm and forearm;
2. weapon sprite registered to a declared socket and pivot;
3. foreground fingers/knuckles.

These are logical draw passes, not a requirement to paint three unrelated
images per pose. A locally rendered vertex-color carrier may encode ownership
and depth masks in one registered source mesh, then deterministically emit the
rear-hand and foreground-finger passes around the independent weapon layer.
The color contract must remain stable across hot swaps and must never be baked
into the final visible palette.

Weapon hot swaps are legal only inside a declared grip class. Collision and damage paths remain independent of artwork.

## Building a novel pose

A novel pose is a recipe, not an untracked redraw:

1. select one or more mined donor atoms;
2. copy only declared joint subsets;
3. apply explicit joint overrides;
4. solve declared contacts and weapon sockets;
5. declare layer occlusion and frame-edge exits;
6. render through the established FPS camera;
7. watch it at intended cadence;
8. promote only after visual acceptance.

This can construct arbitrary candidates without pretending every interpolation is authored acting. Source-derived, generated, manually corrected, rendered, and accepted states remain distinct.

## Initial miner

`scripts/mine_pose_grammar.py` analyzes all 38 Infinite Brutality donor clips. It selects source-exact candidates from endpoints, local motion-energy peaks, and camera-space weapon extrema. It assigns conservative role hints such as `anticipation`, `contact_candidate`, `recovery`, `plant`, or `reach`.

Role hints are navigation, not acceptance. The miner cannot know that a visually plausible frame is the correct shovel contact merely because its transform curve peaks there.

The generated `data/pose_grammar.v1.json` retains exact clip, sample index, time, weapon registration, selection reason, and reconstruction recipe for every atom. The v0 compact rows accidentally dropped weapon registration and reconstruction even though the miner built them internally; v1 repairs that contract.

## Phase-complete mining

Kinematic peaks alone do not make a usable language. The v0 catalog contained
interesting one-handed poses but no `one_hand_long_handle` recoil or recovery
atom, so the first advertised sentence could not be composed without borrowing
an incompatible grip class.

`data/pose_grammar.v1.json` preserves the kinematic discoveries and also pins
the nearest source-exact sample for every semantic phase anchor. The pin is a
coverage rule, not an acting judgment. Phase anchors remain mined candidates.

`scripts/compose_pose_sentence.py` compiles a sentence in two independent
states:

- motion compile: atom identity, role, grip-class compatibility, score order,
  and interruption routes;
- visual compile: registered rear-hand/forearm, weapon, and foreground-finger
  layers for every recipe.

A motion pass cannot promote a visual failure. A flattened accepted image is
premise evidence, not three hot-swappable layers wearing a trench coat.

## Song/score contract

The score chooses pose recipes and timing. It may synchronize accents, holds, ruptures, repeats, or releases to audio markers. It may not silently modify contacts, camera, provenance, layer order, or acceptance state.

This permits a song to conduct combat poses, labor poses, gestures, or cinematic tableaux without creating a separate animation system or baking the soundtrack into the pose assets.

## First proof

The first proof is not another complete attack. It is a small sentence assembled from the grammar:

- source-exact guard atom;
- mined anticipation atom;
- accepted `OneHandAttack2` k004 hard-grip/contact atom;
- mined recoil or recovery atom;
- separate registered hand/weapon/finger layers;
- a short score containing cue, accent, hold, and release.

The proof passes only when the composed first-person watchdown preserves hand identity, weapon path, grip ownership, camera, frame-edge exits, readable low-FPS cadence, and interruption safety.

The initial `OneHandAttack2` sentence passes motion compilation and remains
blocked at visual compilation. Its exact four `Weapon.R +Z` shovel layers now
exist as locally rendered, semantic-vertex-color candidate evidence. Eight
target-identity hand passes remain missing: rear hand/forearm and foreground
fingers for each recipe. The accepted k004 image remains accepted only as
isolated grip/contact premise evidence.

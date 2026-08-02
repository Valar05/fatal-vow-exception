# Fatal Vow — First-Person Hand + Weapon Arcade Workflow

Status: Active workflow contract
Decision authority: Drew Clarke
Adopted: 2026-08-02
Owning project: Fatal Vow Exception
Donor boundary: Infinite Brutality supplies a bounded first-person animation workflow, not Fatal Vow canon.

## Decision

Animate the visible hero hands, forearms, grip, and weapon/tool as one authored low-frame-rate performance.

Reject the alternative of a smoothly interpolated weapon moving without visible hands. Runtime presentation may render at 30 FPS, but the hand-and-tool pose changes on deliberate stepped keys at roughly 8–12 authored poses per second.

## Verified donor truth from Infinite Brutality

The transferable implementation pattern is:

- FPSPlayer.glb is the first-person arm and animation source.
- First-person arms use a separate camera-space render pass so the player does not see chest/body intrusion.
- The established first-person camera mount is part of the performance contract.
- The low-poly hard-edged source silhouette is an art-direction seed.
- PBR material authority is preserved; flatness is diagnosed through lighting, UVs, material response, and render-pass setup rather than by deleting material information.
- Poseclip attacks load from the project asset URL directly.
- Browser-visible results require current-build screenshots or frame sheets; parse checks do not prove visual success.
- Pose Lab remains the upstream authoring and transfer surface.

Donor sources:

- Valar05/infinite-brutality/PROJECT_ORIENTATION.md
- Valar05/infinite-brutality/assets/asset_manifest.json
- Valar05/infinite-brutality/docs/POSE_LAB_CLIP_GRADIENT_EDITOR.md
- Valar05/infinite-brutality/AGENTS.md
- Fatal Vow Game Design Document sections 11.4 and 15.2

## Required source artifacts

1. FPSPlayer.glb (5) as the source performance and weapon-bone reference.
2. The accepted hero hand plate as identity, material, silhouette, cuff, forearm, and grip authority.
3. The intended Fatal Vow tool mesh.
4. The established FPS camera mount.
5. An extracted source-motion record for the weapon/tool bone.

The weapon-motion record must include action name, source FPS, frame/time, bone name, parent chain, coordinate basis, local position, and local rotation quaternion. It is required evidence, not optional telemetry. As of adoption, this extraction is still missing.

## Authoring sequence

1. Lock the hero hand plate. Confirm consistent anatomy, skin, wear, sleeve, wrist reinforcement, and grip language. Show palms, backs, outer lateral sides, relaxed curl, and working grips. Full lateral forearms must be visible. No straight square or rectangular cutoff may masquerade as a sleeve end.
2. Extract source motion. Record the weapon/tool bone position and quaternion rotation from FPSPlayer.glb (5) before generating replacement motion.
3. Preserve the performed path. Use Drew's source performance and the established FPS camera. Do not independently invent a prettier tool arc.
4. Select semantic keys. Choose anticipation, commitment, contact, force transfer, recovery, and deliberate stop. Remove dead frames; do not smooth away impact or held intent.
5. Bind hand and tool. The grip owns the tool at every key. Wrist, fingers, handle, working end, and tool axis must read as one coupled object.
6. Author the arcade clip. Use stepped pose timing at approximately 8–12 authored poses per second. Hold keys for readability. Render the game at full frame rate without interpolating the hands and tool into mush.
7. Review both truths. Compare the source/contact sheet, transferred 3D performance, established FPS camera, and in-game result. Orbit diagnostics may explain attachment; first-person framing decides usability.
8. Promote only after visual acceptance. A rig receipt, extracted curve, valid file, or green test does not accept the motion.

## Hero hand plate acceptance

- Same hand identity and costume in every view.
- Five correct, separated fingers where visible.
- Readable palms, backs, wrists, outer lateral forearms, and grip ownership.
- Whole side silhouettes rendered from fingers through the forearm/sleeve transition.
- No square arm cutoffs, floating hands, cropped wrists, or sleeve blocks.
- Materials remain honest: skin, woven fiber, hide, cord, wood, metal, ceramic, or other source-supported matter.
- No unsupported fantasy armor, tactical gloves, literal fleshpunk, or generic hero musculature.
- Grip poses anticipate shovel-kata: slide, reverse, brace, socket strike, pack, withdraw, release, and stop.

## Motion acceptance

- Hand and tool move as one coupled performance.
- Tool path matches extracted source evidence unless Drew authors and accepts a replacement.
- Low-frame timing reads as intentional arcade cadence, not dropped frames.
- Contact, load transfer, recovery, and stopping remain visible.
- No weapon-only smooth animation under frozen or missing hands.
- No camera substitution.
- No acceptance without first-person visual review.

## Capability state at adoption

- Workflow: documented.
- Hero plate: candidate generated; not yet accepted.
- Source GLB: registered.
- Weapon-bone position/rotation extraction: requested, not implemented or verified.
- Runtime hand-and-tool clip: not implemented.

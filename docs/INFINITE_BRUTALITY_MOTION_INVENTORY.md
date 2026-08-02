# Fatal Vow — Infinite Brutality Motion Inventory

Status: Extracted donor evidence  
Source: ChatGPT Library `FPSPlayer.glb (5)` — `libfile_6ed0f03b95c4819189e609333180cbfa`  
Source SHA-256: `9be07cf0e46e2ed97abca38a8a6cf1bbd7c111cec3fa9671c1b0b721c37535da`  
Extraction date: 2026-08-02  
Donor boundary: motion evidence only; this does not import Infinite Brutality canon.

## Result

The source contains 38 embedded glTF animation clips. Their native key grid is 24 FPS. The exact extraction preserves:

- every native channel and key value for every animated node;
- each channel's original `STEP` or `LINEAR` interpolation;
- `Weapon.R` and `Weapon.L` local transforms;
- derived weapon transforms in model space;
- derived weapon transforms relative to the animated `Camera` node;
- the source coordinate basis and both weapon parent chains.

The compact repository manifest is `data/infinite_brutality_motion_manifest.json`. The exact donor and exact 2.9 MB corpus are now public repository inputs at `assets/motion/source/FPSPlayer.glb (5)` and `assets/motion/reference/motion_corpus.json`. The corpus remains mirrored in ChatGPT Library as stable identity `libfile_eff00dae99a88191b64658eff5315c74`, version 0. Its SHA-256 is `d46a66f76355e01c348e7dbab91ef3fd838d0eaf564d8ec6e983a37ea950ab22`.

`tools/extract_fpsplayer_motions.py` reproduces both repository JSON artifacts byte-for-byte from the donor. `tools/validate_weapon_motion.py` independently verifies source/corpus hashes, all 38 clips, 5,440 native transform channels, quaternion normalization, and the inherited camera-space weapon motion required when the arms are removed.

## Complete clip set

| # | Clip | Family | Duration | Native samples |
|---:|---|---|---:|---:|
| 0 | Climbing | traversal | 1.250 s | 31 |
| 1 | ClimbingSide | traversal | 1.250 s | 31 |
| 2 | FistAttack1 | fist attack | 0.708 s | 18 |
| 3 | FistAttack2 | fist attack | 0.833 s | 21 |
| 4 | FistAttack3 | fist attack | 0.833 s | 21 |
| 5 | FistAttack4 | fist attack | 0.833 s | 21 |
| 6 | FistAttackAir | fist attack | 0.750 s | 19 |
| 7 | FistAttackAirForward | fist attack | 1.042 s | 26 |
| 8 | FistAttackCrouch | fist attack | 1.125 s | 28 |
| 9 | FistBlockHitLeft | defense/hurt | 0.375 s | 10 |
| 10 | FistPowerAttack | fist attack | 1.375 s | 34 |
| 11 | FistPowerAttackForwardOld | fist attack | 0.917 s | 23 |
| 12 | FistPowerAttackNeutral | fist attack | 1.167 s | 29 |
| 13 | FistReady | fist ready | 1.250 s | 31 |
| 14 | FistWalking | locomotion | 0.750 s | 19 |
| 15 | JumpAddative | air locomotion | 0.417 s | 11 |
| 16 | KnifeAttack1 | knife attack | 1.250 s | 31 |
| 17 | KnifeAttack2 | knife attack | 1.250 s | 31 |
| 18 | KnifeAttack3 | knife attack | 1.250 s | 31 |
| 19 | KnifeAttack4 | knife attack | 1.250 s | 31 |
| 20 | KnifePowerAttackAir | knife attack | 1.000 s | 25 |
| 21 | KnifePowerAttackForward | knife attack | 1.250 s | 31 |
| 22 | KnifePowerAttackLeft | knife attack | 1.250 s | 31 |
| 23 | KnifePowerAttackNeutral | knife attack | 1.292 s | 32 |
| 24 | KnifeReadied | knife ready | 1.250 s | 31 |
| 25 | KnifeReady | knife ready | 1.250 s | 31 |
| 26 | LandAdditive | air locomotion | 0.417 s | 11 |
| 27 | Mantle | traversal | 1.000 s | 25 |
| 28 | OneHandAttack1 | one-hand attack | 1.250 s | 31 |
| 29 | OneHandAttack2 | one-hand attack | 1.250 s | 31 |
| 30 | OneHandAttack3 | one-hand attack | 1.250 s | 31 |
| 31 | OneHandAttack4 | one-hand attack | 1.250 s | 31 |
| 32 | OneHandReadied | one-hand ready | 1.250 s | 31 |
| 33 | OneHandReady | one-hand ready | 1.250 s | 31 |
| 34 | WandFire | wand attack | 0.333 s | 9 |
| 35 | WandReadied | wand ready | 0.542 s | 14 |
| 36 | WandReady | wand ready | 1.250 s | 31 |
| 37 | OneHandAttack1.002 | sparse overlay | 1.250 s | 2 |

## Weapon basis

- `Weapon.R` parent chain: `Armature → Root → ShoulderCenter → Arm.R → Forearm.R → Hand.R → Weapon.R`
- `Weapon.L` parent chain: `Armature → Root → ShoulderCenter → Arm.L → Forearm.L → Hand.L → Weapon.L`
- Quaternion order: `x, y, z, w`
- glTF basis: right-handed, +Y up; the camera looks down local -Z with +X right.
- The corpus timeline is the union of all native channel key times. It is not resampled or smoothed.

## Source-version discrepancy

Infinite Brutality's later `PLAYER_HURT_AND_ENEMY_SWEEP_NOTES.md` confirms `FistInjuredRight`, `FistBlockHitParry`, and `FistReadied` in the runtime GLB used for that build. Those clips are absent from this exact Library source, while `FPSPlayer.glb (5)` contains the 38 clips listed above. They remain documented donor history, not fabricated members of this extraction.

## Fatal Vow use

The one-hand and knife families are the strongest source candidates for shovel and sword reduction. They are motion evidence, not automatically accepted Fatal Vow animations. Promotion still requires:

1. select a source clip;
2. inspect the source in the established FPS camera;
3. choose deliberate semantic keys at roughly 8–12 FPS;
4. bind the accepted hands and tool as one performance;
5. visually review contact, load transfer, recovery, and stop;
6. obtain Drew's acceptance.

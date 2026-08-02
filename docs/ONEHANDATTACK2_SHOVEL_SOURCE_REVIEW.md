# OneHandAttack2 Shovel Source Review

Updated: 2026-08-02  
Status: source motion selected; first identity-transfer master remains red

## Authority lock

- Motion: `FPSPlayer.glb (5)`, SHA-256 `9be07cf0e46e2ed97abca38a8a6cf1bbd7c111cec3fa9671c1b0b721c37535da`, clip `OneHandAttack2`, native 24 FPS, 1.25 seconds.
- Camera: Infinite Brutality arms runtime, vertical FOV 82°, 16:9, animated `Camera` node plus `(0, 0.015, 0)`, looking along +Z.
- Tool: `Meshy_AI_Low_Poly_Tools_and_Tr_0802140452_texture.glb`, SHA-256 `f6e86e2a7a65061b8575ecbf3afd5d32e396716b21f57353718d3e9f66cfbd1a`.
- Identity: accepted `Medieval Fleshpunk Hand Turnaround Sheet.png`, ChatGPT Library `libfile_8466a8dd2b408191a489cefda59013c3`.
- Product invariant: candidate motion = source motion; candidate identity = accepted target identity.

## Selection

Visual review selected `OneHandAttack2` for the first shovel path. `KnifeAttack1` remains the leading sword source for a separate later pass. `OneHandAttack3` was rejected because the striking hand/tool travel offscreen for too much of the action.

The shovel binds to `Weapon.R` longitudinal +Z (blue in the diagnostic overlays). An initial +Y bind drove the shovel head through the camera and hid the striking hand during recovery; that bind is rejected and preserved only as evidence.

| Key | Source time | Source event |
|---|---:|---|
| k001 | 0.000 s | guarded start |
| k002 | 0.083 s | anticipation begins |
| k003 | 0.208 s | left crossing extreme |
| k004 | 0.250 s | fast re-entry and reversal |
| k005 | 0.333 s | rightward catch |
| k006 | 0.625 s | high-right reach extreme |
| k007 | 0.792 s | recovery landing |
| k008 | 1.250 s | held endpoint |

These are source keys, not an authored timing revision. No in-betweens or hit-stop have been added.

## Identity-transfer review

The single load-bearing k004 redraw passed the premise: readable five-finger closure, accepted wrist/cuff identity, source camera, and shovel contact. SHA-256: `e5b472dbe5dc97c8e2a9a61c02f43cc8c89aaa3cc4254bcd6fc67f0c74990857`.

Three whole-sheet attempts remain rejected:

1. The 4×2 sheet squeezed each 16:9 source cell toward square: camera forgery.
2. The first 3×3 sheet preserved aspect but enlarged/recentered early poses and completed offscreen shovel geometry: motion and tool drift.
3. The strict edit preserved source composition much better, but k001–k003 retain open or ambiguous right-hand closure and the full-sheet k004 grip is weaker than the frozen accepted premise: grip collapse.

No whole-sheet candidate is promoted. No runtime, sprite sheet, or accepted animation exists yet.

## Next gate

Build a small canonical hand/grip part adapter from the accepted plate plus the good k004 solution. Reconstruct k001–k003 first against the locked blue shovel pixels and source wrist anchors. When all grip-critical frozen pairs pass, reconstruct k005–k008, split deterministically, restore source exposure, and perform an intended-speed key-only watchdown. Arcade timing remains blocked until Drew accepts that runtime.


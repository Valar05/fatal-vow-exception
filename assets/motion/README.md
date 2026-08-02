# Arm-free weapon motion reference

`source/FPSPlayer.glb (5)` is the exact public donor GLB, SHA-256
`9be07cf0e46e2ed97abca38a8a6cf1bbd7c111cec3fa9671c1b0b721c37535da`.
`reference/motion_corpus.json` is its byte-reproducible 38-clip extraction,
SHA-256 `d46a66f76355e01c348e7dbab91ef3fd838d0eaf564d8ec6e983a37ea950ab22`.

For weapon-only playback, use each clip's
`weapon_samples[].weapons["Weapon.R"].camera` translation, `rotation_xyzw`, and
scale. Those samples bake the visible hierarchy inherited through
`Hand.R → Forearm.R → Arm.R → ShoulderCenter → Root`; copying only the local
weapon node would discard much of the authored arc.

Run:

```sh
python3 tools/extract_fpsplayer_motions.py \
  'assets/motion/source/FPSPlayer.glb (5)' /tmp/fatal-vow-motion

python3 tools/validate_weapon_motion.py \
  'assets/motion/source/FPSPlayer.glb (5)' \
  assets/motion/reference/motion_corpus.json
```

This is source/reference authority, not a promoted Fatal Vow animation. The
static exporter duplicate `OneHandAttack1.002` remains present and explicitly
flagged instead of being hidden or promoted.

# Fatal Vow — First-Person Pose Grammar and Arcade Performance Workflow

Status: Active workflow contract
Decision authority: Drew Clarke
Adopted: 2026-08-02; grammar revision adopted 2026-08-02
Owning project: Fatal Vow Exception
Donor boundary: Infinite Brutality supplies bounded motion evidence, not Fatal Vow canon.

## Decision

The visible hero hands, forearms, grip, and weapon/tool must read as one authored low-frame-rate performance. They do not have to be one bitmap or one runtime object.

Runtime presentation uses three registered sprite layers:

1. rear hand/palm and forearm;
2. weapon/tool;
3. foreground fingers/knuckles.

Reject smooth weapon-only motion under frozen or absent hands. The game may render at 30 FPS while the visible performance changes on deliberate stepped keys at roughly 8–12 authored poses per second.

Do not build every animation as an isolated strip. Mine reusable source-exact pose atoms, classify their contacts and constraints, and compose performances as scores over pose recipes. Gameplay actions, cinematics, demonstrations, and songs use the same grammar.

## Verified donor truth

- `FPSPlayer.glb (5)` is the first-person arm and motion source.
- The exact corpus contains 38 clips and 5,427 native transform channels with no resampling.
- The established FPS camera mount is part of the performance contract.
- `Weapon.R` +Z is the corrected shovel binding for `OneHandAttack2`.
- First-person arms use a separate camera-space presentation so chest/body intrusion does not replace the intended view.
- Contact sheets remain human-readable source, acceptance surface, and correction language.
- Browser-visible results require current first-person frames or watchdowns; parse checks do not prove visual success.

## Authoring units

- **Pose atom:** one source-exact skeletal state with provenance.
- **Contact atom:** declared hand/tool, foot/ground, body/prop, or other coupled relationship.
- **Layer atom:** registered rear-hand, weapon, or foreground-finger visual.
- **Transition:** an allowed route between compatible atoms with explicit locks.
- **Score event:** cue, accent, hold, release, repeat, interrupt, transition, or stop.
- **Pose recipe:** donor atoms, joint subsets, overrides, contacts, sockets, occlusion, camera, and status.

Rejected performances may be composted into valid atoms, constraints, transitions, or failure evidence. Rejection does not promote any part automatically.

## Required sources

1. `FPSPlayer.glb (5)` and `motion_corpus.json` as source performance evidence.
2. `Medieval Fleshpunk Hand Turnaround Sheet.png` as accepted hand identity, material, silhouette, cuff, forearm, and grip authority.
3. The intended Fatal Vow tool mesh or source-locked render.
4. The established FPS camera mount.
5. A declared grip class, socket, pivot, layer order, and collision path.

## Authoring sequence

1. Mine candidate pose atoms from native source transforms. Preserve clip, sample index, time, coordinate basis, and weapon registration.
2. Classify candidates by domain, role hint, grip class, contact, visibility, and constraint needs. A label such as `contact_candidate` is navigation, not acceptance.
3. Build a pose recipe by copying declared joint subsets from donor atoms, adding explicit overrides, and solving declared contacts.
4. Bind visual layers through the established camera. Freeze source-locked weapon geometry; author back-hand and foreground-finger occlusion separately.
   Register the hand/cuff to the weapon socket and the forearm to an explicit wrist-to-frame-edge exit; one rigid transform is insufficient for first-person foreshortening.
5. Compose a score. Holds and abrupt changes are authored timing, not missing interpolation.
6. Render contact sheets and a first-person watchdown at intended cadence.
7. Promote only after visual acceptance. Source-derived, generated, manually corrected, rendered, and accepted states remain separate.

## Hot-swap contract

Weapons may hot-swap only inside a declared grip class with compatible socket, pivot, hand separation, occlusion, and reach. One-handed swords and compatible tools may share a contract. A shovel, axe, or two-handed implement may require a different contact and layer set even when it borrows the same body motion.

Collision, damage, and gameplay state are independent of sprite artwork. A visual swap cannot silently change gameplay reach or force.

## Hero hand acceptance

- Same accepted hand identity and costume in every view.
- Five correct, separated fingers where visible.
- Readable grip ownership and correct rear/front occlusion.
- Full lateral forearms with natural tapered sleeve transitions.
- No square cutoffs, floating hands, cropped wrists, generic forearms, or reconstructed source-locked tools.
- No unsupported fantasy armor, tactical gloves, literal fleshpunk, or generic hero musculature.

## Motion acceptance

- Hands and tool read as one coupled performance even though runtime layers remain separate.
- Tool path matches source evidence unless Drew authors and accepts a replacement.
- Contacts, force transfer, recovery, deliberate stopping, and frame-edge exits remain visible.
- Low-frame timing reads as intentional arcade cadence.
- No camera substitution and no acceptance without first-person visual review.

## Current capability state

- Hero hand identity: accepted.
- Source motion extraction: implemented and tested for 38 clips / 5,427 channels.
- Pose grammar miner: implemented and deterministic.
- Mined pose catalog: 297 source-exact candidates in 33 semantic families; not visually accepted as a set.
- `OneHandAttack2` isolated k004 hard grip: accepted as premise evidence.
- Complete grammar-composed runtime sentence: not yet implemented or accepted.
- First grammar-composed carrier sentence: implemented and locally rendered as a candidate; all twelve layer artifacts compile. It is not user accepted or runtime integrated.

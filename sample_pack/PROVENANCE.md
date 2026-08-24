# Sample-pack provenance

## Summary

All twelve PNG files in this fictional benchmark were created for Visual
Release Gate on 2026-08-23 using OpenAI's built-in image-generation mode. No
third-party images, logos, characters, trademarks, or confidential source
materials were supplied as inputs. The brand name ExampleCo and its visual
policy are fictional.

The generated images were used as returned and renamed into `references/` and
`assets/`. Their inclusion in this repository is governed by the generation
service terms that applied at creation time. The guide and structured benchmark
data are offered under CC-BY-4.0 as described in `DATA_LICENSE.md`.

## Final prompt set

The prompts deliberately request a consistent fictional illustration system:
midnight navy, sky blue, coral, warm cream, rounded modular geometry, large
negative space, and no legible branding beyond copy explicitly requested for a
test case.

### Approved references

1. `ref_001.png`: a wide editorial vector illustration of an adult cyclist in
   a clearly readable riding pose, in the fictional palette, with crisp flat
   modular shapes and generous negative space.
2. `ref_002.png`: a wide editorial vector illustration of an adult presenting
   a smartphone, with hand, gaze, and device contact clearly readable, using
   the same fictional palette and flat modular system.
3. `ref_003.png`: a wide editorial vector illustration of an adult sitting in
   a relaxed, clearly supported pose, with rounded geometry and spacious warm
   cream composition.
4. `ref_004.png`: a wide editorial vector illustration of an adult in an
   energetic dance pose, with clear limb direction, crisp fills, and the same
   fictional visual language.

### Review targets

1. `target_01.png`: a policy-aligned adult cyclist with a clearly readable
   riding action.
2. `target_02.png`: a policy-aligned adult holding and presenting a smartphone;
   the pose is intentionally not a wave.
3. `target_03.png`: an adult in an intentionally ambiguous seated/leaning pose,
   preserving multiple plausible readings.
4. `target_04.png`: an adult holding a blank rectangular campaign sign with no
   visible text.
5. `target_05.png`: an adult holding a campaign sign with the exact legible copy
   `START NOW`.
6. `target_06.png`: an intentional style violation with glossy three-dimensional
   forms, obvious volumetric gradients, highlights, and cast shadows.
7. `target_07.png`: an intentional color-hierarchy violation in which coral
   dominates the subject and composition.
8. `target_08.png`: a policy-aligned energetic airborne dance/jump pose with
   clearly readable body direction.

All prompts also requested an original, fictional composition; no logo; no
watermark; no recognizable public figure; and no extra legible text.

## SHA-256 manifest

```text
71b6ebc6dee8f17cad3773086a752659cf66a140f3abd436d3f205ee0b733823  references/ref_001.png
ac71222d9bd7de703d02ebfe73dd730c324ee630528ccc681a14ade10a90679b  references/ref_002.png
52b0f846ea7290b0e0c57335af8db1a0e39be972f92b8e4149eaee567861825d  references/ref_003.png
c68ff96a6eb8b07362011cb3545fd08753e8487536d5b3e3ea31e90ebfe0427a  references/ref_004.png
25aaf328be3ac05c3fcfd86f71bb31230eb058dce98f7fea878ac5a71739fc2e  assets/target_01.png
2e0f3b557fdbd1957a823bd27055148b0f50231a7134601790b652bb28bc93af  assets/target_02.png
30c7e9eb0263ce986a6a5df775be23d4c5c98156fab2d9b48932450a3f9e2364  assets/target_03.png
d3be1887e61aae8a43814868bcd346a710ba79ef1a4e66bb0c02158e650c969b  assets/target_04.png
48fee0a64a27939de276f15a7d2f54590074ef7890d1dc21769c802ae19793c1  assets/target_05.png
f69b0d692a9bb1120e0acf314842860b1392b7604ffc481948a51a4885054e3b  assets/target_06.png
6ee0825417a09131b4cda9de71155cd2749ffd099a11d2c0593bf9240e5c971b  assets/target_07.png
4f616d99774562bc2b5184780b6ae30bfe3ee84d2855dbf130bf635948fb9494  assets/target_08.png
```

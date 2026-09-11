# README Visual Assets

This directory contains language-neutral assets shared by `README.md` and `README.zh-CN.md`.

## Included

| File | Purpose | Source |
| --- | --- | --- |
| `hero.png` | 16:9 project hero; exactly two UAVs in a narrow indoor competition course | Generated concept visualization; no embedded text or logo |
| `corridor-flight.jpg` | Close corridor-navigation view | Original RflySim screenshot supplied by the project owner |
| `dual-uav-corridor.jpg` | Both aircraft visible inside the narrow course | Original RflySim screenshot supplied by the project owner |
| `dual-uav-platforms.jpg` | Dual-UAV overview with raised course obstacles | Original RflySim screenshot supplied by the project owner |

The Hero image is a concept visualization, not live-test evidence. README capability claims must continue to link to repository evidence documents.

## Recommended simulation screenshots

When the original RflySim screenshots are available inside the repository, curate copies here using stable, descriptive names:

| Target filename | Recommended source view | Treatment |
| --- | --- | --- |
| `rviz-planning.png` | UAV1/UAV2 RViz planning view | Crop UI chrome only when it does not remove diagnostic context |
| `demo.gif` | 5–10 second dual-UAV traversal | Loop cleanly; target ≤10 MB for comfortable GitHub loading |

Do not link an asset from the root README until the file is committed. Do not reference ignored `logs/` or `generated/` paths directly. Avoid embedded prose so the same asset works in both language editions.

## Export guidelines

- Prefer PNG for UI/simulation captures and WebP for large photographic assets when repository tooling supports it.
- Keep still images near 1600×900 and optimize them before commit.
- Preserve the original screenshot separately when cropping or annotating.
- Never use a concept image as evidence for a live validation claim.

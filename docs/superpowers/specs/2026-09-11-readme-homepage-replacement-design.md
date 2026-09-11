# README Homepage Replacement Design

## Goal

Replace the repository homepage with the prepared bilingual content under
`RflySim-FutureCraft-README/`, including every image referenced by that content.

## Selected Approach

- Replace the root `README.md` with `RflySim-FutureCraft-README/README.md`.
- Add the Chinese homepage as root `README.zh-CN.md`.
- Copy `RflySim-FutureCraft-README/docs/assets/readme/` into
  `docs/assets/readme/`, preserving relative paths used by both README files.
- Remove the temporary `RflySim-FutureCraft-README/` source directory after its
  tracked content has been transferred. Do not copy `.DS_Store` files.

This preserves the prepared English-first homepage and its Chinese language
switch while avoiding broken image links or macOS metadata in the repository.

## Scope and Safety

Only documentation and README assets change. No simulator, lifecycle, ROS,
mission, planner, sensor, arming, or flight-baseline behavior is modified.
Existing unrelated working-tree changes must remain untouched.

## Validation

1. Compare the destination README files and assets against their sources before
   removing the temporary directory.
2. Confirm all local links referenced by both root README files resolve.
3. Run `tests/script_inventory_check.py`, `tests/docs_link_check.py`, and
   `scripts/validate_repository.ps1` as required by the prepared README.
4. Review the final Git diff and confirm no `.DS_Store` file is included.


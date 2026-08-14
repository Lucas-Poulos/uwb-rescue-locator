# Shared libraries

Symbols, footprints, and 3D models used on **both** the wristband and the bay
station -- the clearest example is whatever UWB IC/module gets chosen, since
it appears on both boards.

- `symbols/uwb_rescue_locator_shared.kicad_sym`
- `footprints/uwb_rescue_locator_shared.pretty/`
- `3dmodels/`

Both board projects register this library in their `fp-lib-table` /
`sym-lib-table` under the nickname `uwb_rescue_locator_shared`, referenced
via `${KIPRJMOD}/../shared/...` so it resolves correctly no matter where the
repo is cloned.

If a part is only used on one board, put it in that board's own `libs/`
folder instead -- don't add it here.

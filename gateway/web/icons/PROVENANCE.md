# Gateway icon family

The 52 selectable application icons in `catalog.json` use a square 96 × 96 viewBox, the same 76 × 76 tile at (10, 8) in the macOS continuous-corner shape (squircle, corner radius 22.37 % of the side), a white-to-pale-blue chassis, a thin glass rim and a subtle shadow. Glyphs remain centered, colorful and individually drawn as editable SVG paths; there are no embedded bitmaps, font dependencies or remote requests. Existing gateway icons are retained.

The additional application artwork was drawn for this project on 2026-10-23 and is distributed under the repository's license. It uses simplified, recognizable visual references to named software. Product names and trademarks belong to their respective owners; the drawings are shortcuts for identifying user-selected links and do not imply endorsement or official affiliation. No external icon packs or third-party SVG source were copied.

The compact `refresh.svg`, `trash.svg`, and `sort.svg` files are utility menu glyphs and are deliberately excluded from the application chooser. `add.svg` remains an existing tile-shaped action icon and is also excluded from the chooser.

The local shortcuts `hermes` and `workbuddy` use original gateway-family glyphs (winged H and friendly overlapping chat bubbles), rather than claiming to reproduce an official brand asset. Additional frequently deployed local services include AList, File Browser, Proxmox and n8n.

`account.svg` (person with a security shield) and `routes.svg` (fixed-exit map pin) are original control-panel glyphs drawn for the settings window in the same tile family. Like the utility glyphs, they are not listed in the application chooser.

`files.svg`, `nas.svg`, `photos.svg`, `settings.svg` and `dns.svg` were redrawn on 2026-11-26 so that each differs from `folder.svg`, `server.svg`, `immich.svg` and `openwrt.svg`.

## Gateway app icons

The gateway's own apps (`apps/*.webp`) and its favicon, `favicon.ico`, `favicon-32.png`, `favicon.svg` and `apple-touch-icon.png` were made for this project on 2026-11-26. The artwork was generated with an image model from original text prompts; no logo, screenshot or third-party artwork was used as input. Each picture was then masked to the same squircle tile as the SVG family, given a glass rim and a shadow, and exported at 256 × 256. They are distributed under the repository's license.

## Settings icons

`settings/*.svg` follow the current macOS System Settings sidebar: a squircle in a system-style colour with a soft top-to-bottom gradient, a thin light rim and a large white glyph in the manner of SF Symbols. The glyphs were drawn for this project on 2026-11-26 as original SVG paths in `gateway/scripts/build-icons.py`; no Apple symbol, font or artwork was copied.


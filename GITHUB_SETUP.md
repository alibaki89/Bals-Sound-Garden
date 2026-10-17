# Bal's Sound Garden — GitHub Source & Pages Setup

This repository is intended for the original source and a public project website. **No GitHub Releases are used.** Installer downloads remain on [itch.io](https://abprojects.itch.io/bals-sound-garden).

**GitHub Pages:** Repository Settings → Pages → Build and deployment → Deploy from a branch → `main` / `/docs` → Save. The web page will be served at `https://alibaki89.github.io/Bals-Sound-Garden/`.

**Local source:** See [BUILDING.md](BUILDING.md).

**Publishing:** The prepared PowerShell script prompts before creating the new repository. It refuses to replace an existing repository. The active `gh` account should be `alibaki89`.

**Licensing:** The original source code uses MIT. Creative assets and screenshots are excluded from the blanket code license. See `LICENSE`, `LICENSE.md`, `ASSETS_LICENSE.md` and `ASSET_LICENSE_REVIEW.md`. Confirm distribution rights for the listed creative assets before public publication.

**Screenshots:** Run `py .\Import-Itch-Screenshots.py` from the extracted repository folder *before* publishing. It retrieves the official itch.io cover and gallery images, records their original URLs and checksums, and inserts them into README and Pages. The publisher refuses to run until the gallery manifest exists.

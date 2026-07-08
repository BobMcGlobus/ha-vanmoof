# Brand assets

Source artwork for the integration's icon/logo (self-drawn bicycle silhouette +
Helvetica "S3/X3" wordmark, in VanMoof yellow).

- `icon.svg` — vector source of the icon.
- `icon.png` (256×256), `icon@2x.png` (512×512) — square icon.
- `logo.png` (512×176), `logo@2x.png` (1024×352) — wordmark (@2x is exactly 2×).

## How the icon reaches Home Assistant

Since **Home Assistant 2026.3**, custom integrations ship their brand images
themselves — no PR to `home-assistant/brands` is needed (that repo now rejects
custom-integration icons; see
https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api).

The images HA actually serves live in **`custom_components/vanmoof/brand/`**
(`icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`). Local brand images take
priority over the brands CDN. This `brands/` folder is just the source of truth;
keep the two in sync (copy the PNGs into `custom_components/vanmoof/brand/` after
changing them here).

On HA older than 2026.3 the icon won't show (no local brand support); everything
else works regardless.

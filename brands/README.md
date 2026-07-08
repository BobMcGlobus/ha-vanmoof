# Brand assets

Home Assistant shows an integration's logo/icon from the central
[`home-assistant/brands`](https://github.com/home-assistant/brands) repo — it is
**not** loaded from this repo. Until a brand is submitted there, the UI shows
"logo not available" placeholders.

`icon.svg` here is only a **source/placeholder**. Replace it with official VanMoof
artwork you have the right to use before submitting.

## How to add the icon (one-time)

1. Export PNGs from the artwork (transparent background, trimmed to content,
   square):
   - `icon.png` — 256×256
   - `icon@2x.png` — 512×512
   - optionally `logo.png` / `logo@2x.png` (wordmark, max 512 px on the long side)
2. Fork `home-assistant/brands` and add them under **custom integrations**:
   ```
   custom_integrations/vanmoof/icon.png
   custom_integrations/vanmoof/icon@2x.png
   ```
3. Open a PR. Once merged, HA/HACS show the icon automatically and the
   `ignore: brands` line in `.github/workflows/validate.yml` can be removed.

No image tooling was available where this was scaffolded, so the PNG export is
left as a manual step.

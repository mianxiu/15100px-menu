Fonts exported losslessly from Blender 5.2.1 LTS (9e2066aef7ef), installed locally.

- Inter.ttf: Inter.woff2 decoded to SFNT, unmodified outlines and font names.
- NotoSansCJK.otf: Noto Sans CJK Regular.woff2 decoded to SFNT, unmodified outlines and names.
- COPYRIGHT.txt: copyright and license notices extracted from the font name tables.
- OFL-1.1.txt: SIL Open Font License text distributed with Blender.

Build-time conversion uses fontTools with WOFF2/Brotli support; no fontTools dependency at runtime.
Blender uses em-based FreeType sizes. Our stb_truetype adapter multiplies by hhea (ascent-descent)/unitsPerEm: Inter 2478/2048, Noto 1448/1000.

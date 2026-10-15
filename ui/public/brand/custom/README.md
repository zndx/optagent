# Custom brand pack

Settings → Branding empty slot uploads a `.tgz`. Layout:

**Flat**

```
logo.svg
favicon.svg
brand.json   # optional
```

**Weathership kit**

```
brand/logo/lockup/lockup-mono-white.svg
brand/favicon/favicon.svg
```

The process stores the normalized pack under
`SIGNALS_UI_BRAND_CUSTOM` (default `build/dev/.signals-ui-brand/custom`).

Product name and UI copy stay **Signals** — only logo assets swap.

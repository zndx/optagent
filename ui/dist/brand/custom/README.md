# Custom brand pack

Settings → Branding empty slot uploads a `.tgz`. Layout:

**Flat**

```
logo.svg
favicon.svg
brand.json      # optional
logo-small.txt  # optional, 5 lines of 10 characters, same box as the harness mark
logo.txt        # optional, 7 lines of 14 characters, the taller mark
```

**Weathership kit**

```
brand/logo/lockup/lockup-mono-white.svg
brand/favicon/favicon.svg
```

The process stores the normalized pack under
`SIGNALS_UI_BRAND_CUSTOM` (default `build/dev/.signals-ui-brand/custom`).

Product name and UI copy stay **Signals** — only logo assets swap.

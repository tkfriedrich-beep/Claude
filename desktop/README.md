# Otto.app — desktop launcher

A double-clickable macOS app that boots the AgenticOS Cockpit locally and opens it in your
browser. It's a thin launcher, not a packaged binary — the Cockpit is local-first (FastAPI +
Next.js), so "live" means it runs on your Mac.

## Install

1. Drag `Otto.app` onto your Desktop (or into `/Applications`).
2. **First launch only:** right-click `Otto.app` → **Open** → **Open**. macOS blocks unsigned
   downloaded apps on a plain double-click; after doing this once, normal clicks work.
   Terminal equivalent: `xattr -dr com.apple.quarantine /path/to/Otto.app`.

## What it does on click

1. Opens a Terminal window (you may be asked once to allow Otto to control Terminal).
2. Finds the Cockpit repo — in this order: the folder it lives inside (if you run it in place),
   `~/.otto-repo`, common locations (`~/Claude`, `~/Developer/Claude`, …), or it offers to
   `git clone` it to `~/Claude`.
3. On first run: `make setup` + `make demo` (a few minutes). After that it's fast.
4. `make dev` (control plane `:8787` + web `:3000`), then opens <http://localhost:3000>.

Quit by closing the Terminal window (both servers stop cleanly).

## Requirements on the Mac

`git`, [`uv`](https://astral.sh/uv), Node.js 20+, and `pnpm`. Otto checks for each and prints the
exact install command for anything missing. Optional: `FIRECRAWL_API_KEY` for live web search
(everything else, including page fetch, runs keyless); a local `claude` login or
`ANTHROPIC_API_KEY` for the live Claude runtime (otherwise Otto runs an offline demo).

## Rebuilding

```bash
make app          # regenerates the icon (desktop/make_icon.py) + marks the launcher executable
```

The icon is generated deterministically by `desktop/make_icon.py` (Pillow, run via
`uv run --with pillow`); `Otto.icns` is packed by hand so no macOS tools are needed. Edit the
launcher at `desktop/Otto.app/Contents/MacOS/Otto`.

Runs entirely on your Mac — nothing is hosted or sent anywhere; Safe Mode is on by default.

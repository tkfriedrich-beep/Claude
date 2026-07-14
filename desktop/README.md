# Otto desktop launchers

Double-clickable macOS apps that boot the AgenticOS Cockpit and open it in your browser. They're
thin launchers, not packaged binaries — the Cockpit is local-first (FastAPI + Next.js), so "live"
means it runs on your Mac. Two variants:

| App | Icon | Runs | Reach it at |
| --- | --- | --- | --- |
| **Otto.app** | indigo | `make dev` — localhost only | <http://localhost:3000> on the Mac |
| **Otto (Phone).app** | champagne gold | `make phone` — all interfaces | `http://<Mac-Tailscale-IP>:3000` from your phone (and localhost on the Mac) |

Both share the same repo, setup, and `~/.otto-repo` config — pick the one that matches how you
want to reach the cockpit right now.

## Install

1. Drag `Otto.app` and/or `Otto (Phone).app` onto your Desktop (or into `/Applications`).
2. **First launch only:** right-click the app → **Open** → **Open**. macOS blocks unsigned
   downloaded apps on a plain double-click; after doing this once, normal clicks work.
   Terminal equivalent: `xattr -dr com.apple.quarantine "/path/to/Otto (Phone).app"`.

## Otto (Phone) — viewing on your phone over Tailscale

`Otto (Phone).app` binds both servers to your network so a phone on the same
[Tailscale](https://tailscale.com) tailnet can reach them. On launch it prints the exact URL —
`http://<this-Mac's-Tailscale-IP>:3000` — which you open in your phone's browser. No per-device
config: the UI derives the control-plane address from the host you loaded, and CORS already
allows tailnet origins.

**Security:** this makes the *unauthenticated* control plane reachable to anything on that
network. Keep **Safe Mode ON** (external writes stay blocked; every action is approval-gated).
Do **not** run `tailscale funnel` on these ports — that would publish Otto to the public
internet. See `docs/RUNBOOK.md` → "View on your phone (Tailscale)" for the tailnet-only option
(`make phone PHONE_HOST=100.x.y.z`).

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
make app          # regenerates both icons + marks both launchers executable
```

Icons are generated deterministically by `desktop/make_icon.py` (Pillow, via `uv run --with
pillow`; `--variant default|phone`); the `.icns` files are packed by hand so no macOS tools are
needed. Edit the launchers at `desktop/Otto.app/Contents/MacOS/Otto` and
`desktop/Otto (Phone).app/Contents/MacOS/Otto Phone`.

Runs entirely on your Mac — nothing is hosted or sent anywhere; Safe Mode is on by default.

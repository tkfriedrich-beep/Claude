# Web Research connector (`web`)

Read-only web access for the **Research Run** skill. Two tools:

| Tool | What it does |
| --- | --- |
| `web.search` | Search the web → ranked `{title, url, snippet}`. Firecrawl-backed when a key is set; offline demo fallback otherwise. |
| `web.fetch` | Fetch one public `http(s)` URL → readable text. Keyless, SSRF-guarded. |

## Configuration

- **Live search** needs a Firecrawl key. Set `FIRECRAWL_API_KEY` in the environment (or
  `services/control-plane/.env`). The key is referenced by name through `SecretStore` and never
  stored in the DB, events, or logs. Without it, `web.search` returns a clearly `demo`-labeled
  placeholder and `web.fetch` still works on any public URL.
- Per-workspace overrides via the connector row config: `api_key_env` (default
  `FIRECRAWL_API_KEY`), `search_provider` (`firecrawl` | `offline`), `max_bytes`.

## Security

- **SSRF guard** on `web.fetch`: only `http`/`https`; the host must resolve *entirely* to public
  addresses — loopback, private (RFC1918), link-local (incl. the `169.254.169.254` cloud-metadata
  endpoint), reserved, multicast, and unspecified addresses are refused. Redirects are followed
  manually and **every hop is re-validated**, so a public URL cannot bounce into the internal
  network. Non-text `Content-Type` and oversized bodies are rejected.
- **Content is data, not instructions.** Fetched page text is untrusted; the Research Run skill
  passes it to the model as reference material and tells the model to ignore any instructions
  embedded inside it.
- These tools make outbound requests (a page fetch / a search query leaves the machine) but
  mutate nothing, so they are classified `access: read`, `external_side_effects: false`, and are
  not blocked by Safe Mode. Add a policy `confirm` rule if you want them approval-gated.

## Known residual (MVP)

DNS rebinding between the guard's resolution and httpx's own connect is not closed in the MVP
(would require pinning the connection to the validated IP). Tracked in THREAT_MODEL.md.

"""Network access guard — who may reach the control plane over the wire.

The MVP is single-user and unauthenticated *by design* (BUILD_BRIEF: local-first, one
operator, localhost). That exception was only ever safe because the socket listened on
loopback. `make phone` opens the socket to a reachable interface so a phone can reach the
cockpit over Tailscale — which, left unguarded, would expose the unauthenticated API
(settings, Safe Mode, approvals, policies, connector management) to the whole LAN.

This guard closes that gap at the edge, before any route or workspace lookup runs:

  * loopback is always allowed (localhost dev, the Mac itself, in-process tests);
  * plus an allowlist of trusted networks — by default the Tailscale CGNAT range
    100.64.0.0/10, i.e. your own tailnet devices;
  * everything else is rejected with 403, even though the socket accepted the TCP
    connection.

CORS is browser ergonomics (it does nothing against curl or a native client); THIS is the
actual access boundary. It is deliberately conservative: a peer we cannot identify as a real
remote IP (no client, or a non-IP host such as Starlette's in-process "testclient") is treated
as local — a network attacker always presents a real routable address. Widen or disable via
COCKPIT_TRUSTED_NETWORKS (e.g. "0.0.0.0/0,::/0" to allow all — opt-in, documented).
"""

from __future__ import annotations

import ipaddress
from functools import lru_cache

_IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=32)
def parse_networks(spec: str) -> tuple[_IPNetwork, ...]:
    """Parse a comma-separated CIDR list into networks, skipping empty/invalid entries."""
    nets: list[_IPNetwork] = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            nets.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            # A malformed entry must never silently widen access — drop it.
            continue
    return tuple(nets)


def client_is_trusted(host: str | None, trusted_spec: str) -> bool:
    """True if a client at ``host`` may reach the control plane.

    Loopback and any address inside ``trusted_spec`` (comma-separated CIDRs) are trusted.
    A missing or non-IP host is trusted: those only arise from in-process ASGI callers, never
    a real remote peer (uvicorn always sets ``request.client`` to the peer's ``(ip, port)``).
    """
    if not host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    if ip.is_loopback:
        return True
    return any(ip in net for net in parse_networks(trusted_spec))

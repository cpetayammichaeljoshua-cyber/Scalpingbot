"""
Shared DNS fallback resolver for the Unity Engine / MiroFish bot.
================================================
This host cannot resolve external DNS (Android-network nameservers), which
made EVERY outbound HTTPS call fail:
  - api.telegram.org        -> no Telegram signals sent
  - fapi.binance.com        -> no klines/tickers -> no signals generated
  - integrate.api.nvidia.com -> LLM (G0DM0D3) unreachable

This module provides a drop-in `aiohttp` resolver that:
  1. Tries the system resolver first (normal hosts, zero overhead).
  2. Falls back to Cloudflare DNS-over-HTTPS (https://cloudflare-dns.com/
     dns-query?name=<host>&type=A) when system DNS fails.  DoH resolves ANY
     hostname correctly on ANY host regardless of local DNS state.

It also exposes `doh_resolve(host)` for synchronous callers.

Usage (aiohttp connector):
    from SignalMaestro.unity_dns import DohFallbackResolver
    resolver = DohFallbackResolver()
    connector = aiohttp.TCPConnector(resolver=resolver, ...)
"""

import asyncio
import json
import logging
import socket as _socket

logger = logging.getLogger("UnityEngine.DNS")

# Cloudflare DoH endpoint (reachable via IP on DNS-broken hosts).
_DOH_URL_TMPL = "https://cloudflare-dns.com/dns-query?name={host}&type=A"
_DOH_IP = "1.1.1.1"          # Cloudflare DNS-over-HTTPS (verified reachable)
_DOH_HOST = "cloudflare-dns.com"
_DOH_TIMEOUT = 6.0

# Cache of hostname -> [ip, ...] resolved via DoH (small TTL to avoid hammering).
_doh_cache = {}
_doh_cache_ttl = 120.0


async def _doh_lookup(host: str, port: int = 443) -> list:
    """Resolve `host` via Cloudflare DNS-over-HTTPS. Returns list of IP strings."""
    import aiohttp

    url = _DOH_URL_TMPL.format(host=host)
    try:
        # Use a short-lived session with the DoH host pinned to its known IP.
        resolver = aiohttp.TCPConnector(
            resolver=_HardcodedHostResolver({_DOH_HOST: _DOH_IP}),
            ttl_dns_cache=60,
        )
        async with aiohttp.ClientSession(connector=resolver) as sess:
            async with sess.get(
                url,
                headers={"accept": "application/dns-json"},
                timeout=aiohttp.ClientTimeout(total=_DOH_TIMEOUT),
            ) as r:
                if r.status != 200:
                    return []
                # NOTE: Cloudflare returns Content-Type: application/dns-json,
                # which aiohttp's .json() rejects. Parse text manually.
                data = json.loads(await r.text())
    except Exception as e:
        logger.debug(f"DoH lookup failed for {host}: {e}")
        return []

    ips = []
    if data.get("Status") == 0:
        # Answer may be CNAME -> follow to the A records.
        cname_target = None
        for ans in data.get("Answer", []):
            if ans.get("type") == 1:  # A record
                ips.append(ans.get("data", ""))
            elif ans.get("type") == 5:  # CNAME
                cname_target = ans.get("data", "")
        # If only a CNAME came back, resolve the target too.
        if not ips and cname_target:
            return await _doh_lookup(cname_target, port)
    return [ip for ip in ips if ip]


class _HardcodedHostResolver:
    """Minimal resolver that maps specific hosts to fixed IPs (for reaching DoH)."""

    def __init__(self, mapping: dict):
        self._mapping = mapping

    async def resolve(self, host, port=0, family=_socket.AF_INET):
        if host in self._mapping:
            return [{
                "hostname": host, "host": self._mapping[host], "port": port,
                "family": family, "proto": _socket.IPPROTO_TCP,
                "flags": _socket.AI_NUMERICHOST,
            }]
        raise OSError(f"_HardcodedHostResolver: no mapping for {host}")

    async def close(self):
        pass


class DohFallbackResolver:
    """aiohttp resolver: system DNS first, Cloudflare DoH fallback.

    Use with aiohttp.TCPConnector(resolver=DohFallbackResolver(), ...).
    """

    def __init__(self, loop=None):
        self._loop = loop or asyncio.get_event_loop()
        self._closed = False

    async def resolve(self, host, port=0, family=_socket.AF_INET):
        # 1) System resolver (normal hosts).
        try:
            infos = await self._loop.run_in_executor(
                None, _socket.getaddrinfo, host, port, family, _socket.SOCK_STREAM
            )
            if infos:
                return [{
                    "hostname": host, "host": info[4][0], "port": info[4][1],
                    "family": info[0], "proto": info[2], "flags": info[3],
                } for info in infos]
        except Exception:
            pass

        # 2) Cloudflare DoH fallback (DNS-broken hosts).
        ips = await _doh_lookup(host, port)
        if ips:
            return [{
                "hostname": host, "host": ip, "port": port,
                "family": family, "proto": _socket.IPPROTO_TCP,
                "flags": _socket.AI_NUMERICHOST,
            } for ip in ips]

        raise OSError(f"DohFallbackResolver: cannot resolve {host}")

    async def close(self):
        self._closed = True


async def doh_resolve(host: str, port: int = 443) -> list:
    """Async: resolve `host` via Cloudflare DoH (system-DNS first)."""
    try:
        infos = await asyncio.get_event_loop().run_in_executor(
            None, _socket.getaddrinfo, host, port, _socket.SOCK_STREAM
        )
        if infos:
            return list({info[4][0] for info in infos})
    except Exception:
        pass
    return await _doh_lookup(host, port)


def resolve_ip(host: str) -> str:
    """Sync convenience: return the first IP for `host` (DoH fallback) or ''."""
    try:
        return _socket.gethostbyname(host)
    except Exception:
        pass
    try:
        return asyncio.run(_doh_lookup(host))
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Global socket.getaddrinfo fallback (covers httpx / aiohttp / requests).
# ─────────────────────────────────────────────────────────────────────────────
_orig_getaddrinfo = _socket.getaddrinfo
_doh_patch_installed = False


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """socket.getaddrinfo that falls back to Cloudflare DoH on DNS failure.

    Safe from BOTH sync and async contexts: if a running event loop is
    detected (asyncio.run() would raise), the DoH lookup is executed on a
    worker thread so it never blocks or corrupts the loop.
    """
    try:
        return _orig_getaddrinfo(host, port, family, type, proto, flags)
    except Exception:
        pass
    # Fallback: resolve via DoH and synthesize an addrinfo tuple.
    try:
        ips = _doh_cache_get(host)
        if not ips:
            ips = _resolve_doh_threadsafe(host, port or 443)
            if ips:
                _doh_cache_set(host, ips)
        if not ips:
            raise
        results = []
        for ip in ips:
            results.append((_socket.AF_INET, _socket.SOCK_STREAM, _socket.IPPROTO_TCP, "",
                            (ip, port)))
        return results
    except Exception:
        raise


def _resolve_doh_threadsafe(host, port):
    """Run the DoH lookup on a worker thread (safe from any event-loop state)."""
    def _run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_doh_lookup(host, port))
            finally:
                loop.close()
        except Exception:
            return []
    # Always run on a fresh thread to avoid a running-loop conflict entirely.
    import threading
    _box = {}
    def _worker():
        _box["ips"] = _run()
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=_DOH_TIMEOUT + 2.0)
    return _box.get("ips", [])


_doh_cache_data = {}
_doh_cache_time = {}


def _doh_cache_get(host):
    import time as _t
    now = _t.time()
    if host in _doh_cache_data and now - _doh_cache_time.get(host, 0) < _doh_cache_ttl:
        return _doh_cache_data[host]
    return []


def _doh_cache_set(host, ips):
    import time as _t
    _doh_cache_data[host] = ips
    _doh_cache_time[host] = _t.time()


def install_doh_fallback():
    """Install the global socket.getaddrinfo DoH fallback. Idempotent."""
    global _doh_patch_installed
    if _doh_patch_installed:
        return
    try:
        _socket.getaddrinfo = _patched_getaddrinfo
        _doh_patch_installed = True
        logger.info("DNS-over-HTTPS fallback installed (socket.getaddrinfo patched)")
    except Exception:
        _doh_patch_installed = False

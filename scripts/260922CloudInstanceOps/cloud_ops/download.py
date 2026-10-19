import hashlib
import ipaddress
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .security import PolicyError


def validate_url(url, policy, resolver=socket.getaddrinfo):
    p = urlsplit(url)
    if p.scheme.lower() != "https" or not p.hostname or p.username is not None or p.password is not None:
        raise PolicyError("Only HTTPS URLs without embedded credentials are allowed")
    if p.port not in (None, 443):
        raise PolicyError("Only HTTPS port 443 is enabled")
    if p.query or p.fragment:
        raise PolicyError("Query/fragment URLs are disabled in v1; do not pass signed links or tokens through CLI")
    host = p.hostname.encode("idna").decode("ascii").lower()
    if host not in policy["allowed_hosts"]:
        raise PolicyError("Download host is outside configured sources: " + host)
    addresses = sorted({r[4][0] for r in resolver(host, 443, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise PolicyError("Source resolves to a non-public address")
    return {"host": host, "resolved_addresses": addresses}


def download(url, filename, expected, observe, state, policy, audit,
             resolver=socket.getaddrinfo, opener_factory=None):
    if (not filename or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,179}", filename)
            or filename.endswith(".") or filename.split(".")[0].upper() in
            {"CON", "PRN", "AUX", "NUL", *("COM" + str(n) for n in range(1, 10)),
             *("LPT" + str(n) for n in range(1, 10))}):
        raise PolicyError("Provide a plain safe filename, without directories")
    if not expected and not observe:
        raise PolicyError("Expected SHA256 required; --observe-hash explicitly records an unverified download")
    if expected and not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
        raise PolicyError("Invalid SHA256")
    if expected and observe:
        raise PolicyError("Choose expected SHA256 or observation mode, not both")
    audit.event("download.requested", url=url, filename=filename,
                initiator_surface="local_windows", verification="expected_hash" if expected else "observed_only",
                note="Resolved IPs are DNS results, not an authenticated peer-IP audit")
    initial = validate_url(url, policy, resolver)
    audit.event("download.source.allowed", **initial)
    class CheckedRedirect(urllib.request.HTTPRedirectHandler):
        redirects = 0
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            self.redirects += 1
            destination = urljoin(req.full_url, newurl)
            if self.redirects > policy.get("max_redirects", 5):
                raise PolicyError("Too many redirects")
            audit.event("download.redirect.requested", source=req.full_url,
                        destination=destination, http_status=code)
            resolved = validate_url(destination, policy, resolver)
            audit.event("download.redirect.allowed", destination=destination, **resolved)
            return super().redirect_request(req, fp, code, msg, headers, destination)
    opener = (opener_factory or urllib.request.build_opener)(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), CheckedRedirect())
    staging = Path(state) / "staging"
    output = Path(state) / "downloads"
    staging.mkdir(exist_ok=True)
    output.mkdir(exist_ok=True)
    temporary = staging / (audit.id + ".part")
    final = output / (audit.id + "__" + filename)
    started, count, digest = time.monotonic(), 0, hashlib.sha256()
    max_bytes = int(policy.get("max_bytes", 209715200))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CloudInstanceOps/1.0", "Accept-Encoding": "identity"})
        with opener.open(req, timeout=15) as response, temporary.open("xb") as f:
            audit.event("download.response", url=response.geturl(), http_status=response.status,
                        content_type=response.headers.get("Content-Type", ""))
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise PolicyError("Download exceeds configured byte limit")
            while True:
                if time.monotonic() - started > policy.get("max_seconds", 120):
                    raise PolicyError("Download exceeds time limit")
                data = response.read(65536)
                if not data:
                    break
                count += len(data)
                if count > max_bytes:
                    raise PolicyError("Download exceeds configured byte limit")
                digest.update(data)
                f.write(data)
            f.flush()
            os.fsync(f.fileno())
        measured = digest.hexdigest()
        if expected and measured != expected.lower():
            audit.event("download.hash_mismatch", expected_sha256=expected.lower(), actual_sha256=measured, size=count)
            raise PolicyError("Downloaded content does not match expected SHA256")
        if final.exists():
            raise PolicyError("Output file already exists")
        # Windows rename fails on an existing destination. UUID destination is
        # also unique on POSIX; this directory is private to the operator.
        temporary.rename(final)
        result = {"file": str(final), "sha256": measured, "size": count,
                  "verification": "matched_expected_hash" if expected else "unverified_observed_hash",
                  "executed": False}
        audit.event("download.saved", **result)
        return result
    finally:
        if temporary.exists():
            temporary.unlink()  # Only this operation's generated partial file.

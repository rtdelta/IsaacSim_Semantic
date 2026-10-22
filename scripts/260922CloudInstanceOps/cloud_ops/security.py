import ctypes
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit


class PolicyError(Exception):
    pass


class Redactor:
    """Best-effort field/pattern redaction, plus exact runtime secret matching.

    This cannot recognize arbitrary, unlabelled or obfuscated business secrets.
    Never use it as permission to read an entire environment or credential file.
    """
    SENSITIVE = re.compile(
        r"(?:password|passwd|passphrase|pwd|token|secret|authorization|"
        r"cookie|api[_-]?key|access[_-]?key|private[_-]?key|credentialblob)", re.I)
    PAIR = re.compile(
        r'''(?P<key>["']?(?:[\w.-]*(?:password|passwd|passphrase|pwd|token|secret|api[_-]?key|access[_-]?key|authorization|cookie)[\w.-]*)["']?\s*[:=]\s*)(?P<value>"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}]+)''', re.I)
    URL = re.compile(r"https?://[^\s<>\"']+", re.I)
    PRIVATE = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?(?:-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|\Z)", re.S)
    AUTH = re.compile(r"(?im)^(\s*(?:authorization|proxy-authorization|cookie|set-cookie)\s*:)\s*[^\r\n]*")
    TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{15,}|github_pat_[A-Za-z0-9_]{15,}|sk-[A-Za-z0-9_-]{20,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b")

    def __init__(self, secrets=()):
        self.secrets = set()
        for secret in secrets:
            self.add_secret(secret)

    def add_secret(self, secret):
        if secret:
            self.secrets.update((secret, quote(secret, safe=""), quote_plus(secret),
                                 json.dumps(secret, ensure_ascii=False)[1:-1]))

    @staticmethod
    def safe_url(value):
        try:
            p = urlsplit(value)
            host = p.hostname or ""
            if ":" in host:
                host = "[" + host + "]"
            if p.port:
                host += ":" + str(p.port)
            return urlunsplit((p.scheme, host, p.path,
                               "REDACTED_QUERY" if p.query else "", ""))
        except ValueError:
            return "[INVALID_URL_REDACTED]"

    def text(self, value):
        value = str(value)
        for secret in sorted(self.secrets, key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        value = self.PRIVATE.sub("[REDACTED_PRIVATE_KEY]", value)
        value = self.AUTH.sub(r"\1 [REDACTED]", value)
        value = re.sub(r"(?i)\bBearer\s+[^\s,;\"']+", "Bearer [REDACTED]", value)
        value = self.PAIR.sub(lambda m: m.group("key") + "[REDACTED]", value)
        value = self.TOKEN.sub("[REDACTED_TOKEN]", value)
        value = self.URL.sub(lambda m: self.safe_url(m.group()), value)
        # Strip terminal control characters, retaining readable tabs/newlines.
        value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value)

    def clean(self, value):
        if isinstance(value, dict):
            return {self.text(k): "[REDACTED]" if self.SENSITIVE.search(str(k))
                    else self.clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(v) for v in value]
        return self.text(value) if isinstance(value, str) else value

    def reject_sensitive_text(self, text, label):
        if self.text(text) != text:
            raise PolicyError(label + " contains secret-like data, URL queries or control characters; use a credential reference and a minimal script")


def private_directory(path):
    """Protect only the tool's own state root; never touch system/workspace ACLs."""
    path = Path(path).expanduser().absolute()
    if path.is_symlink():
        raise PolicyError("State directory must not itself be a symlink/junction")
    # Packaged Windows apps may transparently redirect LOCALAPPDATA. Resolve
    # that actual location, then require our marker before touching existing data.
    path = path.resolve()
    marker = path / ".cloud-instance-ops-state"
    if path.exists() and not marker.is_file() and any(path.iterdir()):
        raise PolicyError("Refusing to alter permissions of a nonempty directory not owned by this tool")
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        who = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                             capture_output=True, check=True, text=True)
        match = re.search(r"S-1-5-(?:\d+-)*\d+", who.stdout)
        if not match:
            raise PolicyError("Cannot determine current Windows user SID")
        result = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r",
                                 "*" + match.group() + ":(OI)(CI)F",
                                 "*S-1-5-18:(OI)(CI)F"], capture_output=True)
        if result.returncode:
            raise PolicyError("Cannot restrict audit state directory permissions")
    else:
        path.chmod(0o700)
    if not marker.exists():
        marker.write_text("CloudInstanceOps private state v1\n", encoding="utf-8")
    return path


class WindowsCredentials:
    """Generic Windows credentials, current-user scope. Values never in argv."""
    def __init__(self):
        if os.name != "nt":
            raise PolicyError("This credential provider requires Windows; use key authentication on other systems")
        from ctypes import wintypes as w
        class Credential(ctypes.Structure):
            _fields_ = [("Flags", w.DWORD), ("Type", w.DWORD), ("TargetName", w.LPWSTR),
                        ("Comment", w.LPWSTR), ("LastWritten", w.FILETIME),
                        ("CredentialBlobSize", w.DWORD),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", w.DWORD), ("AttributeCount", w.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", w.LPWSTR),
                        ("UserName", w.LPWSTR)]
        self.Credential = Credential
        self.dll = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self.dll.CredReadW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD,
                                       ctypes.POINTER(ctypes.POINTER(Credential))]
        self.dll.CredReadW.restype = w.BOOL
        self.dll.CredWriteW.argtypes = [ctypes.POINTER(Credential), w.DWORD]
        self.dll.CredWriteW.restype = w.BOOL
        self.dll.CredFree.argtypes = [ctypes.c_void_p]

    def read(self, name):
        p = ctypes.POINTER(self.Credential)()
        if not self.dll.CredReadW(name, 1, 0, ctypes.byref(p)):
            raise PolicyError("Credential reference unavailable in Windows Credential Manager")
        try:
            return ctypes.string_at(p.contents.CredentialBlob,
                                    p.contents.CredentialBlobSize).decode("utf-16-le")
        finally:
            self.dll.CredFree(p)

    def write(self, name, username, secret):
        if not secret:
            raise PolicyError("Empty credentials are not stored")
        blob = secret.encode("utf-16-le")
        if len(blob) > 2560:
            raise PolicyError("Credential too large")
        buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        c = self.Credential()
        c.Type, c.TargetName, c.UserName = 1, name, username
        c.Comment = "CloudInstanceOps SSH authentication; never export to logs"
        c.CredentialBlobSize, c.CredentialBlob = len(blob), buf
        c.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE, still scoped to this user.
        try:
            if not self.dll.CredWriteW(ctypes.byref(c), 0):
                raise PolicyError("Windows Credential Manager write failed")
        finally:
            ctypes.memset(buf, 0, len(blob))


def load_policy(path):
    policy_path = Path(path)
    if not policy_path.is_file():
        template = policy_path.with_name(policy_path.stem + ".example" + policy_path.suffix)
        raise PolicyError("Local policy missing: create and fill " + str(template) + " as " + str(policy_path))
    data = json.loads(policy_path.read_text(encoding="utf-8-sig"))
    if data.get("schema") != 1:
        raise PolicyError("Unsupported policy schema")
    # Authentication is exclusively by reference or local key path.
    for name, target in data.get("targets", {}).items():
        if any(k in target for k in ("password", "token", "secret", "private_key")):
            raise PolicyError("Literal secrets are forbidden in target profiles")
        if not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", target.get("host_fingerprint", "")):
            raise PolicyError("A pinned host fingerprint is required for " + name)
        if not re.fullmatch(r"[a-f0-9]{64}", target.get("machine_id_sha256", "")):
            raise PolicyError("A recorded machine identity is required for " + name)
    return data

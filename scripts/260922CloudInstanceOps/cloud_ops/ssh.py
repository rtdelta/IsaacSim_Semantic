import base64
import hashlib
import json
import shlex
import time

from .security import PolicyError, WindowsCredentials


class OutcomeUnknown(Exception):
    """A remote command may still be running, or have partially completed."""


def key_fingerprint(key):
    return "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")


def check_fingerprint(key, expected):
    if key_fingerprint(key) != expected:
        raise PolicyError("SSH host fingerprint mismatch; authentication refused")


def check_identity(actual, target):
    if (actual.get("machine_id_sha256") != target["machine_id_sha256"] or
            actual.get("hostname") != target["hostname"]):
        raise PolicyError("Instance identity mismatch; project command refused")


def collect(channel, timeout=30, max_output=1048576):
    """Drain both streams to avoid deadlock. No raw output is written to disk.

    If a stream exceeds the limit, discard it in full: truncating first could
    expose the prefix of a secret that straddles the truncation boundary.
    """
    deadline = time.monotonic() + timeout
    buffers, total, exceeded = [bytearray(), bytearray()], [0, 0], [False, False]
    while True:
        for i, ready, receive in ((0, channel.recv_ready, channel.recv),
                                  (1, channel.recv_stderr_ready, channel.recv_stderr)):
            if ready():
                part = receive(65536)
                total[i] += len(part)
                if total[i] > max_output:
                    exceeded[i] = True
                    buffers[i].clear()
                elif not exceeded[i]:
                    buffers[i].extend(part)
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
            code = channel.recv_exit_status()
            if code < 0:
                raise OutcomeUnknown("SSH closed without a remote exit status")
            return {"exit_code": code,
                    "stdout": "[OUTPUT_OMITTED_SIZE_LIMIT]" if exceeded[0] else buffers[0].decode("utf-8", "replace"),
                    "stderr": "[OUTPUT_OMITTED_SIZE_LIMIT]" if exceeded[1] else buffers[1].decode("utf-8", "replace"),
                    "output_bytes": total, "output_omitted": exceeded}
        if time.monotonic() >= deadline:
            raise OutcomeUnknown("SSH command timeout; remote completion is unknown; no automatic retry or process termination")
        time.sleep(0.01)


IDENTITY_SCRIPT = """import hashlib,json,os
print(json.dumps({'hostname':os.uname().nodename,'machine_id_sha256':hashlib.sha256(open('/etc/machine-id','rb').read()).hexdigest()}))
"""


def remote_python(client, script, audit, label, timeout, cwd=None):
    audit.event("ssh.command.requested", label=label,
                script_sha256=hashlib.sha256(script.encode("utf-8")).hexdigest(),
                interpreter="python3 -I -S -B", cwd=cwd, timeout_seconds=timeout)
    command = "python3 -I -S -B -"
    if cwd:
        command = "cd -- " + shlex.quote(cwd) + " && " + command
    channel = client.get_transport().open_session(timeout=15)
    try:
        channel.settimeout(15)
        # Once a request is sent, a transport failure can leave outcome unknown.
        channel.exec_command(command)
        channel.sendall(script.encode("utf-8"))
        channel.shutdown_write()
        result = collect(channel, timeout)
        audit.event("ssh.command.completed", label=label, **result)
        return result
    except OutcomeUnknown:
        raise
    except Exception as exc:
        raise OutcomeUnknown("SSH interrupted after command request; inspect remote state before retry") from exc
    finally:
        channel.close()


def run(target, alias, audit, redactor, script=None, timeout=30, intent="read", credential_provider=None):
    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*Blowfish has been deprecated.*")
        import paramiko
    auth = target.get("auth")
    secret = None
    kwargs = dict(hostname=target["host"], port=int(target["port"]),
                  username=target["username"], look_for_keys=False, allow_agent=False,
                  timeout=15, banner_timeout=15, auth_timeout=15)
    if auth == "windows-credential":
        secret = (credential_provider or WindowsCredentials()).read(target["credential_ref"])
        redactor.add_secret(secret)
        kwargs["password"] = secret
    elif auth == "key":
        kwargs["key_filename"] = target["identity_file"]
        if target.get("passphrase_ref"):
            phrase = (credential_provider or WindowsCredentials()).read(target["passphrase_ref"])
            redactor.add_secret(phrase)
            kwargs["passphrase"] = phrase
    else:
        raise PolicyError("Unsupported authentication provider")
    if script is not None:
        redactor.reject_sensitive_text(script, "Script")
        if len(script.encode("utf-8")) > 262144:
            raise PolicyError("Script exceeds 256 KiB; transfer project code separately")
        audit.snapshot("script", script)
    audit.event("ssh.connect.requested", target_alias=alias, host=target["host"],
                port=target["port"], username=target["username"], auth_method=auth,
                expected_host_fingerprint=target["host_fingerprint"],
                initiator_surface="local_windows", destination_surface="remote_linux",
                declared_intent=intent, intent_is_not_a_sandbox=True)
    class PinnedKey(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            check_fingerprint(key, target["host_fingerprint"])
            audit.event("ssh.host_key.verified", fingerprint=key_fingerprint(key))
    client = paramiko.SSHClient()
    # Deliberately no AutoAddPolicy/TOFU and no key forwarding. A matching pin is
    # required before Paramiko sends the supplied authentication credential.
    client.set_missing_host_key_policy(PinnedKey())
    try:
        client.connect(**kwargs)
        audit.event("ssh.authenticated", target_alias=alias)
        identity = remote_python(client, IDENTITY_SCRIPT, audit, "identity", 15)
        if identity["exit_code"]:
            raise PolicyError("Identity probe failed")
        try:
            actual = json.loads(identity["stdout"])
        except (ValueError, TypeError):
            raise PolicyError("Invalid identity probe response")
        check_identity(actual, target)
        audit.event("ssh.instance.verified", **actual)
        if script is None:
            return {"identity": actual, "target": alias, "exit_code": 0}
        return remote_python(client, script, audit, "user_script", timeout, target["workspace"])
    finally:
        client.close()

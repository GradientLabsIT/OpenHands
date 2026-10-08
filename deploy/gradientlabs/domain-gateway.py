#!/usr/bin/env python3
"""Activate and renew the private OpenHands hostname after DNS delegation."""

import fcntl
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


DOMAIN = "openhands.gradientlabs.it"
ADDRESS = "100.87.94.92"
STATE = Path("/var/lib/openhands-tls")
CERTS = Path("/etc/caddy/certs") / DOMAIN
ROUTE = Path("/etc/caddy/openhands.caddy")
NAMESERVERS = {f"ns{i}.digitalocean.com." for i in range(1, 4)}


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def dns(server, name, kind):
    try:
        result = run(
            ["dig", "@" + server, name, kind, "+short", "+time=5", "+tries=1"],
            capture_output=True, text=True,
        )
    except subprocess.CalledProcessError:
        return set()
    return set(result.stdout.lower().splitlines())


def delegated():
    try:
        result = run([
            "dig", "@a.dns.it", "gradientlabs.it", "NS", "+norecurse",
            "+noall", "+authority", "+time=5", "+tries=1",
        ], capture_output=True, text=True)
    except subprocess.CalledProcessError:
        return False
    records = [line.lower().split() for line in result.stdout.splitlines()]
    return {row[4] for row in records if len(row) == 5 and row[3] == "ns"} == NAMESERVERS


def desired_route():
    return f"""http://{DOMAIN} {{
    bind 127.0.0.1 {ADDRESS}
    redir https://{{host}}{{uri}} 308
}}

https://{DOMAIN} {{
    bind 127.0.0.1 {ADDRESS}
    tls {CERTS}/current/fullchain.pem {CERTS}/current/privkey.pem
    encode gzip zstd
    reverse_proxy 127.0.0.1:18080
}}
"""


def replace_route(text):
    temporary = ROUTE.with_suffix(".tmp")
    temporary.write_text(text)
    temporary.chmod(0o644)
    temporary.replace(ROUTE)


def activate():
    source = STATE / "config/live" / DOMAIN
    fingerprint = hashlib.sha256((source / "fullchain.pem").read_bytes()).hexdigest()
    version = CERTS / fingerprint
    if not CERTS.parent.exists():
        CERTS.parent.mkdir(mode=0o750, parents=True)
        CERTS.parent.chmod(0o750)
        shutil.chown(CERTS.parent, user="root", group="caddy")
    for directory in (CERTS, version):
        directory.mkdir(mode=0o750, parents=True, exist_ok=True)
        directory.chmod(0o750)
        shutil.chown(directory, user="root", group="caddy")
    for name in ("fullchain.pem", "privkey.pem"):
        destination = version / name
        if destination.exists() and destination.read_bytes() == (source / name).read_bytes():
            continue
        with destination.open("wb") as output:
            os.fchmod(output.fileno(), 0o640)
            with (source / name).open("rb") as certificate:
                shutil.copyfileobj(certificate, output)
        shutil.chown(destination, user="root", group="caddy")
    temporary_link = CERTS / "current.tmp"
    temporary_link.unlink(missing_ok=True)
    temporary_link.symlink_to(version.name)
    temporary_link.replace(CERTS / "current")
    previous = ROUTE.read_text() if ROUTE.exists() else "# OpenHands route pending.\n"
    replace_route(desired_route())
    try:
        run(["caddy", "validate", "--config", "/etc/caddy/Caddyfile"])
        run(["systemctl", "reload", "caddy"])
    except Exception:
        replace_route(previous)
        raise
    (STATE / "activated-certificate").write_text(
        hashlib.sha256((source / "fullchain.pem").read_bytes()).hexdigest()
    )
    print("OpenHands custom hostname activated with a valid certificate.")


def main():
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / "lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        certificate = STATE / "config/live" / DOMAIN / "fullchain.pem"
        if certificate.exists():
            result = subprocess.run(
                ["openssl", "x509", "-in", str(certificate), "-checkend", "2592000", "-noout"],
                capture_output=True,
            )
            if result.returncode == 0:
                marker = STATE / "activated-certificate"
                fingerprint = hashlib.sha256(certificate.read_bytes()).hexdigest()
                installed = CERTS / "current/fullchain.pem"
                if (
                    not marker.exists() or marker.read_text() != fingerprint
                    or not ROUTE.exists() or ROUTE.read_text() != desired_route()
                    or not installed.exists()
                    or hashlib.sha256(installed.read_bytes()).hexdigest() != fingerprint
                ):
                    activate()
                print("OpenHands certificate valid for more than 30 days.")
                return
        failure = STATE / "last-issuance-failure"
        if failure.exists():
            try:
                recent_failure = time.time() - float(failure.read_text()) < 21600
            except ValueError:
                recent_failure = False
            if recent_failure:
                print("Certificate issuance retry delayed after a failure.")
                return
        if not delegated():
            print("Waiting for DigitalOcean nameserver delegation.")
            return
        for resolver in ("1.1.1.1", "8.8.8.8"):
            if dns(resolver, DOMAIN, "A") != {ADDRESS}:
                print("Waiting for the OpenHands DNS record.")
                return
        with tempfile.TemporaryDirectory(prefix="credentials-", dir="/run/openhands-tls") as directory:
            credentials = Path(directory) / "digitalocean.ini"
            token = run(
                ["/usr/local/bin/gradient-vault", "--vault", "gradientlabs", "get", "DIGITALOCEAN_API_TOKEN"],
                capture_output=True, text=True,
            ).stdout.strip()
            if not token:
                raise RuntimeError("Vault returned no DigitalOcean token.")
            with credentials.open("w") as output:
                os.fchmod(output.fileno(), 0o600)
                output.write("dns_digitalocean_token = " + token + "\n")
            del token
            command = [
                "certbot", "certonly", "--non-interactive", "--agree-tos",
                "--email", "luca@gradientlabs.it", "--cert-name", DOMAIN,
                "--config-dir", str(STATE / "config"),
                "--work-dir", str(STATE / "work"),
                "--logs-dir", str(STATE / "logs"),
                "--dns-digitalocean", "--dns-digitalocean-credentials", str(credentials),
                "--dns-digitalocean-propagation-seconds", "60", "-d", DOMAIN,
            ]
            failure.write_text(str(time.time()))
            run(command)
        failure.unlink(missing_ok=True)
        activate()


if __name__ == "__main__":
    main()

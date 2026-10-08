"""Install private custom-host TLS activation on the existing platform gateway."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).parent
PLATFORM = "root@100.87.94.92"


def ssh(command, data=None):
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", PLATFORM, command],
        input=data, check=True,
    )


ssh("DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-certbot-dns-digitalocean")
ssh(
    "install -d -m 700 /var/lib/openhands-tls; "
    "cat > /usr/local/sbin/openhands-domain.tmp && chmod 755 /usr/local/sbin/openhands-domain.tmp "
    "&& mv /usr/local/sbin/openhands-domain.tmp /usr/local/sbin/openhands-domain",
    (ROOT / "domain-gateway.py").read_bytes(),
)
for name in ("openhands-domain.service", "openhands-domain.timer"):
    ssh("cat > /etc/systemd/system/" + name, (ROOT / name).read_bytes())
ssh("python3 -", b'''from pathlib import Path
import subprocess

route = Path("/etc/caddy/openhands.caddy")
if not route.exists() or not route.read_text().strip():
    route.write_text("# OpenHands route awaits DNS delegation and certificate issuance.\\n")
config = Path("/etc/caddy/Caddyfile")
previous = config.read_text()
line = "import /etc/caddy/openhands.caddy\\n"
if line not in previous:
    backup = Path("/var/lib/openhands-tls/Caddyfile.before-openhands")
    if not backup.exists():
        backup.write_text(previous)
    config.write_text(previous + "\\n" + line)
    try:
        subprocess.run(["caddy", "validate", "--config", str(config)], check=True)
        subprocess.run(["systemctl", "reload", "caddy"], check=True)
    except Exception:
        config.write_text(previous)
        raise
''')
ssh(
    "systemctl daemon-reload && systemctl enable --now openhands-domain.timer "
    "&& systemctl start openhands-domain.service"
)

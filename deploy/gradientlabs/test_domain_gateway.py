import importlib.util
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "domain_gateway", Path(__file__).with_name("domain-gateway.py")
)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)


class DomainGatewayTests(unittest.TestCase):
    def test_activation_permissions_and_failed_reload_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            source = state / "config/live" / gateway.DOMAIN
            source.mkdir(parents=True)
            (source / "fullchain.pem").write_text("test certificate")
            (source / "privkey.pem").write_text("test private key")
            route = state / "route"
            route.write_text("# Pending certificate.\n")
            certs = state / "new-parent/certs"
            with patch.object(gateway, "STATE", state), patch.object(
                gateway, "ROUTE", route
            ), patch.object(gateway, "CERTS", certs), patch.object(
                gateway.shutil, "chown"
            ), patch.object(gateway, "run", side_effect=[None, subprocess.CalledProcessError(1, ["systemctl", "reload", "caddy"])]):
                previous_umask = os.umask(0o077)
                try:
                    with self.assertRaises(subprocess.CalledProcessError):
                        gateway.activate()
                finally:
                    os.umask(previous_umask)
                self.assertEqual(certs.stat().st_mode & 0o777, 0o750)
                self.assertEqual(certs.parent.stat().st_mode & 0o777, 0o750)
                self.assertEqual((certs / "current").resolve().stat().st_mode & 0o777, 0o750)
                self.assertEqual((certs / "current/privkey.pem").stat().st_mode & 0o777, 0o640)
                self.assertFalse((state / "activated-certificate").exists())
                self.assertEqual(route.read_text(), "# Pending certificate.\n")
                self.assertEqual(route.stat().st_mode & 0o777, 0o644)
                with patch.object(gateway.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), patch.object(
                    gateway, "activate"
                ) as activate:
                    gateway.main()
                    activate.assert_called_once()

    def test_pending_delegation_does_not_request_credentials_or_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(gateway, "STATE", Path(directory)), patch.object(
                gateway, "delegated", return_value=False
            ), patch.object(gateway, "run") as run:
                gateway.main()
                run.assert_not_called()

    def test_valid_certificate_skips_provider_access(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            certificate = state / "config/live" / gateway.DOMAIN / "fullchain.pem"
            certificate.parent.mkdir(parents=True)
            certificate.write_text("test certificate")
            (state / "activated-certificate").write_text(
                hashlib.sha256(certificate.read_bytes()).hexdigest()
            )
            route = state / "route"
            certs = state / "certs"
            installed = certs / "current/fullchain.pem"
            installed.parent.mkdir(parents=True)
            installed.write_bytes(certificate.read_bytes())
            with patch.object(gateway, "STATE", state), patch.object(
                gateway, "ROUTE", route
            ), patch.object(gateway, "CERTS", certs
            ), patch.object(gateway.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), patch.object(
                gateway, "dns"
            ) as dns, patch.object(gateway, "run") as run:
                route.write_text(gateway.desired_route())
                gateway.main()
                dns.assert_not_called()
                run.assert_not_called()

    def test_failed_certificate_request_cleans_private_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary_directory = tempfile.TemporaryDirectory
            paths = []

            def temporary(**kwargs):
                return temporary_directory(prefix=kwargs["prefix"], dir=directory)

            def run(args, **kwargs):
                if args[0] == "/usr/local/bin/gradient-vault":
                    return subprocess.CompletedProcess(args, 0, stdout="test-token\n")
                if args[0] == "certbot":
                    credentials = Path(args[args.index("--dns-digitalocean-credentials") + 1])
                    self.assertEqual(credentials.stat().st_mode & 0o777, 0o600)
                    paths.append(credentials)
                    raise subprocess.CalledProcessError(1, args)
                self.fail("Unexpected command")

            with patch.object(gateway, "STATE", Path(directory) / "state"), patch.object(
                gateway, "dns", return_value={gateway.ADDRESS}
            ), patch.object(gateway, "delegated", return_value=True
            ), patch.object(gateway.tempfile, "TemporaryDirectory", side_effect=temporary), patch.object(
                gateway, "run", side_effect=run
            ), patch.object(gateway, "activate") as activate:
                with self.assertRaises(subprocess.CalledProcessError):
                    gateway.main()
                activate.assert_not_called()
                self.assertEqual(len(paths), 1)
                self.assertFalse(paths[0].exists())


if __name__ == "__main__":
    unittest.main()

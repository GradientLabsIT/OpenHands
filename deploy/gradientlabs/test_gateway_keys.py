import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('gateway_keys', Path(__file__).with_name('update-authorized-keys.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class GatewayKeysTest(unittest.TestCase):
    def test_preserves_operator_keys_and_replaces_only_gateway(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'authorized_keys'
            operator = 'ssh-ed25519 AAAAoperator operator'
            path.write_text(operator + '\nrestrict ssh-ed25519 AAAAgateway old-comment\n')
            line = 'command="/bin/false",restrict,port-forwarding,permitopen="127.0.0.1:32770" ssh-ed25519 AAAAgateway openhands-gateway'
            module.update(path, line)
            module.update(path, line)
            self.assertEqual(path.read_text().splitlines(), [operator, line])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_refuses_gateway_as_only_remaining_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'authorized_keys'
            old = 'restrict ssh-ed25519 AAAAgateway old-comment\n'
            path.write_text(old)
            with self.assertRaises(RuntimeError):
                module.update(path, 'restrict ssh-ed25519 AAAAgateway openhands-gateway')
            self.assertEqual(path.read_text(), old)

if __name__ == '__main__':
    unittest.main()

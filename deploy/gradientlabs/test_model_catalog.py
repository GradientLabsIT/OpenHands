import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


spec = importlib.util.spec_from_file_location("catalog_patch", Path(__file__).with_name("patch-model-catalog.py"))
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


class ModelCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {
            key: {"default_model": "new-" + key, "package": "@test/" + key, "version": "2.0.0",
                  "available_models": [{"id": "new-" + key, "label": "New " + key}]}
            for key in ("claude-code", "codex")
        }

    def test_python_consumers_receive_models_and_defaults_without_other_changes(self):
        source = '''_CLAUDE_MODELS: tuple = (ACPModelOption(id="old", label="Old"),)
_CODEX_MODELS: tuple = (ACPModelOption(id="old", label="Old"),)
providers = {
 "claude-code": ACPProviderInfo(key="claude-code", available_models=_CLAUDE_MODELS, note="é", default_model="old", secret="claude-auth"),
 "codex": ACPProviderInfo(key="codex", available_models=_CODEX_MODELS, default_model="old", secret="codex-auth"),
 "other": ACPProviderInfo(key="other", available_models=(), default_model="unchanged", secret="other-auth"),
}
'''
        namespace = {"ACPModelOption": SimpleNamespace, "ACPProviderInfo": SimpleNamespace}
        exec(patch.patch_python_registry(source, self.catalog), namespace)
        for key in self.catalog:
            provider = namespace["providers"][key]
            self.assertEqual(provider.available_models[0].id, provider.default_model)
            self.assertEqual(provider.default_model, "new-" + key)
        self.assertEqual(namespace["providers"]["claude-code"].secret, "claude-auth")
        self.assertEqual(namespace["providers"]["other"].default_model, "unchanged")

    def test_client_keeps_authentication_and_updates_launch_pin(self):
        registry = {key: {"default_command": ["npx", "-y", "@test/" + key + "@1.0.0"], "secret_refs": [key + "-auth"]} for key in self.catalog}
        registry["other"] = {"default_model": "unchanged"}
        updated = patch.patch_client_registry(registry, self.catalog)
        for key in self.catalog:
            self.assertEqual(updated[key]["available_models"][0]["id"], updated[key]["default_model"])
            self.assertTrue(updated[key]["default_command"][-1].endswith("@2.0.0"))
            self.assertEqual(updated[key]["secret_refs"], [key + "-auth"])
        self.assertEqual(updated["other"], {"default_model": "unchanged"})

    def test_upstream_registry_drift_is_rejected(self):
        with self.assertRaises(RuntimeError):
            patch.patch_python_registry("models = ()", self.catalog)


if __name__ == "__main__":
    unittest.main()

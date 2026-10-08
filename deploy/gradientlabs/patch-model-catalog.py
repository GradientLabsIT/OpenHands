"""Update the pinned SDK registry and its generated client mirror together."""

import argparse
import ast
import importlib.metadata
import json
from pathlib import Path


def replace_nodes(source, replacements):
    data = source.encode('utf-8')
    lines = data.split(b'\n')
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    edits = []
    for node, value in replacements:
        start = offsets[node.lineno - 1] + node.col_offset
        end = offsets[node.end_lineno - 1] + node.end_col_offset
        edits.append((start, end, value))
    for start, end, value in sorted(edits, reverse=True):
        data = data[:start] + value.encode('utf-8') + data[end:]
    source = data.decode('utf-8')
    ast.parse(source)
    return source


def patch_python_registry(source, catalog):
    model_keys = {"_CLAUDE_MODELS": "claude-code", "_CODEX_MODELS": "codex"}
    edits = []
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            provider = model_keys.get(node.target.id)
            if provider:
                rows = catalog[provider]["available_models"]
                value = "(\n" + "".join(
                    f"    ACPModelOption(id={row['id']!r}, label={row['label']!r}),\n"
                    for row in rows
                ) + ")"
                edits.append((node.value, value))
                found.add((provider, "models"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ACPProviderInfo":
            keywords = {item.arg: item.value for item in node.keywords}
            key = keywords.get("key")
            if isinstance(key, ast.Constant) and key.value in catalog:
                provider = key.value
                edits.append((keywords["default_model"], repr(catalog[provider]["default_model"])))
                found.add((provider, "default"))
    expected = {(key, kind) for key in catalog for kind in ("models", "default")}
    if found != expected:
        raise RuntimeError("Pinned SDK model registry changed; review the deployment patch.")
    return replace_nodes(source, edits)


def patch_client_registry(registry, catalog):
    for key, provider in catalog.items():
        current = registry[key]
        command = current["default_command"]
        matches = [i for i, token in enumerate(command) if token.startswith(provider["package"] + "@")]
        if len(matches) != 1:
            raise RuntimeError("Pinned client ACP command changed: " + key)
        command[matches[0]] = provider["package"] + "@" + provider["version"]
        current["available_models"] = provider["available_models"]
        current["default_model"] = provider["default_model"]
    return registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path)
    parser.add_argument("--sdk", action="store_true")
    args = parser.parse_args()
    catalog = json.loads(Path(__file__).with_name("subscription-models.json").read_text())
    if args.client:
        registry = patch_client_registry(json.loads(args.client.read_text()), catalog)
        args.client.write_text(json.dumps(registry, indent=2) + "\n")
    if args.sdk:
        package = importlib.metadata.distribution("openhands-sdk")
        settings = Path(package.locate_file("openhands/sdk/settings"))
        registry = settings / "acp_providers.py"
        registry.write_text(patch_python_registry(registry.read_text(), catalog))
        install = settings / "acp_install_catalog.py"
        source = install.read_text()
        names = {"CLAUDE_AGENT_ACP_VERSION": "claude-code", "CODEX_ACP_VERSION": "codex"}
        edits = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id in names:
                    edits.append((node.value, repr(catalog[names[target.id]]["version"])))
        if len(edits) != len(names):
            raise RuntimeError("Pinned ACP installation catalog changed.")
        install.write_text(replace_nodes(source, edits))


if __name__ == "__main__":
    main()

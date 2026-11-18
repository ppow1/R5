"""R5 plugin system, Phase 0 DRAFT — NOT DEPLOYED, NOT INSTALLED LIVE.
Date: 2026-11-17. Pat approved Phase 0 start 11:42 EST.

Spirit, not code wholesale:
- R3 r3a_runtime/module_contracts.py (118 lines): semver, version ranges,
  dependency-graph validation, missing/cycle = fail closed at load.
- R3 r3a_plugins/*/manifest.json: digest-pinned artifact, provider
  entrypoint, operation contract, effect_class, required grants, lifecycle.
- R1 RIVERVIEW_MODULE_CONTRACT_V1.md: frozen core owns authority / events /
  diagnostics / registry; modules may do bounded things only; disabling a
  module leaves core healthy; incompatible modules fail closed, do not start.

What was CUT (fine-tooth comb, ChatGPT scrutiny rule):
- R3's 15-25 line controlled headers, file-provenance ceremony, versioned
  contracts + work-order + authorization audit + evidence envelope per
  invocation, provider child-process protocol, full JSON schema apparatus,
  three versions of institutional_knowledge, Bitwarden stack.
- Kept: manifest + semver + dependency graph + digest check + lifecycle
  (discover / validate / register / activate / invoke / replace / stop /
  reload) + the frozen-core boundary, in stdlib-only Python.

Frozen core (R5): socket dispatch, ledger, authority/grants, registry
itself, heartbeat. A plugin may NOT own, replace, or bypass any of these.
Reserved capability names are refused at load. A plugin provides named
capabilities (e.g. "telemetry.read", "hello.greet") and the core invokes
them by name. No plugin is authoritative merely by being installed.
"""
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

CORE_CONTRACT = "r5-core-contract-1.0"
# Capabilities the core owns. A plugin claiming one is rejected, fail closed.
RESERVED_CAPABILITIES = {
    "socket.dispatch", "socket.observe", "socket.monitor",
    "ledger.append", "ledger.read",
    "authority.grant", "authority.revoke", "authority.check",
    "registry.load", "registry.register",
    "heartbeat", "grace.inference",
}
REQUIRED_MANIFEST_FIELDS = ("plugin_id", "plugin_version", "entrypoint", "provides")


def parse_semver(version):
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version or ""))
    if not m:
        raise ValueError(f"version must be major.minor.patch, got {version!r}")
    return tuple(int(x) for x in m.groups())


def version_satisfies(version, expression):
    """Ranges: exact, ==, >=, <=, >, <, ~ (same minor), ^ (same major, 0.x rules),
    comma-separated AND clauses. R3 grammar, rewritten lean."""
    cand = parse_semver(version)
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError("dependency version range must be nonempty")
    for clause in expression.split(","):
        clause = clause.strip()
        m = re.fullmatch(r"([~^])?(\d+\.\d+\.\d+)", clause)
        if m:
            op, raw = m.groups()
            lower = parse_semver(raw)
            if not op:
                if cand != lower:
                    return False
                continue
            if op == "~":
                upper = (lower[0], lower[1] + 1, 0)
            elif lower[0] > 0:
                upper = (lower[0] + 1, 0, 0)
            elif lower[1] > 0:
                upper = (0, lower[1] + 1, 0)
            else:
                upper = (0, 0, lower[2] + 1)
            if cand < lower or cand >= upper:
                return False
            continue
        m = re.fullmatch(r"(>=|<=|>|<|==)?(\d+\.\d+\.\d+)", clause)
        if not m:
            raise ValueError(f"unsupported version range: {expression!r}")
        op, raw = m.groups()
        bound = parse_semver(raw)
        op = op or "=="
        ok = {">=": cand >= bound, "<=": cand <= bound, ">": cand > bound,
              "<": cand < bound, "==": cand == bound}[op]
        if not ok:
            return False
    return True


def validate_manifest(data, plugin_dir):
    """Fail closed: return (errors list). Empty list = valid."""
    errors = []
    if not isinstance(data, dict):
        return ["manifest must be a JSON object"]
    for f in REQUIRED_MANIFEST_FIELDS:
        if not data.get(f):
            errors.append(f"missing required field: {f}")
    try:
        parse_semver(data.get("plugin_version", ""))
    except ValueError as e:
        errors.append(str(e))
    if data.get("schema_version") not in (None, 1):
        errors.append("schema_version must be 1")
    provides = data.get("provides") or []
    if not isinstance(provides, list) or not all(isinstance(p, str) for p in provides):
        errors.append("provides must be a list of capability names")
    else:
        for cap in provides:
            if cap in RESERVED_CAPABILITIES:
                errors.append(f"capability {cap!r} is reserved for the frozen core")
    for dep in data.get("dependencies") or []:
        if not isinstance(dep, dict) or not dep.get("plugin_id") or not dep.get("version_range"):
            errors.append(f"bad dependency entry: {dep!r}")
            continue
        try:
            version_satisfies("0.0.0", dep["version_range"])
        except ValueError as e:
            errors.append(f"bad version_range for {dep['plugin_id']}: {e}")
    entry = data.get("entrypoint") or ""
    if entry and not (Path(plugin_dir) / entry).exists() and ":" not in entry:
        errors.append(f"entrypoint file not found: {entry}")
    return errors


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Plugin:
    def __init__(self, manifest, plugin_dir, module):
        self.manifest = manifest
        self.dir = Path(plugin_dir)
        self.module = module
        self.id = manifest["plugin_id"]
        self.version = manifest["plugin_version"]
        self.status = "registered"  # registered -> active -> stopped / disabled / failed
        self.instance = None

    def activate(self, config=None):
        factory = getattr(self.module, "create_plugin", None)
        if factory is None:
            raise ValueError(f"{self.id}: plugin.py must define create_plugin(config)")
        self.instance = factory(config or self.manifest.get("config") or {})
        self.status = "active"
        return self

    def invoke(self, capability, **kwargs):
        if self.status != "active":
            raise ValueError(f"{self.id} is not active (status={self.status})")
        caps = getattr(self.instance, "capabilities", None)
        if caps is None:
            raise ValueError(f"{self.id}: plugin instance has no capabilities dict")
        fn = caps.get(capability)
        if fn is None:
            raise ValueError(f"{self.id} does not provide {capability!r}")
        return fn(**kwargs)

    def stop(self):
        stop = getattr(self.instance, "stop", None) if self.instance else None
        if callable(stop):
            try:
                stop()
            except Exception:
                pass
        self.instance = None
        self.status = "stopped"


class PluginRegistry:
    """Discover -> validate -> register -> activate -> invoke -> replace/stop.
    Reload rescans manifests: add / disable / remove / replace a plugin by
    changing its manifest directory only. Core code is never edited."""

    def __init__(self, plugins_dir):
        self.dir = Path(plugins_dir)
        self.plugins = {}       # plugin_id -> Plugin (active/registered)
        self.rejected = {}      # plugin_id -> reason (fail closed, core continues)
        self.core_healthy = True

    def _load_manifest(self, plugin_dir):
        mfile = Path(plugin_dir) / "manifest.json"
        if not mfile.exists():
            return None, "no manifest.json"
        try:
            data = json.loads(mfile.read_text())
        except Exception as e:
            return None, f"manifest is not valid JSON: {e}"
        errors = validate_manifest(data, plugin_dir)
        if errors:
            return None, "; ".join(errors)
        # Digest pin, if the manifest pins one: mismatch = reject, do not run.
        pinned = data.get("artifact_sha256")
        entry = data.get("entrypoint", "")
        if pinned and ":" not in entry:
            actual = sha256_file(Path(plugin_dir) / entry)
            if actual != pinned:
                return None, f"artifact digest mismatch for {entry}"
        return data, None

    def _load_module(self, manifest, plugin_dir):
        entry = manifest["entrypoint"]
        path = Path(plugin_dir) / entry
        name = f"r5_plugin_{manifest['plugin_id'].replace('.', '_').replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    def _validate_graph(self, manifests):
        """Missing dependency and cycle = reject the dependent plugin(s).
        Core stays healthy; other plugins still load."""
        by_id = {m["plugin_id"]: m for m in manifests}
        rejected = {}
        # missing / unsatisfiable dependency
        for m in manifests:
            for dep in m.get("dependencies") or []:
                other = by_id.get(dep["plugin_id"])
                if other is None:
                    rejected[m["plugin_id"]] = (
                        f"requires unconfigured {dep['plugin_id']}@{dep['version_range']}")
                elif not version_satisfies(other["plugin_version"], dep["version_range"]):
                    rejected[m["plugin_id"]] = (
                        f"requires {dep['plugin_id']}@{dep['version_range']}, "
                        f"found {other['plugin_version']}")
        # cycle detection (DFS, only over not-yet-rejected plugins)
        visiting, visited = set(), set()
        graph = {m["plugin_id"]: [d["plugin_id"] for d in m.get("dependencies") or []
                                  if d["plugin_id"] in by_id]
                 for m in manifests if m["plugin_id"] not in rejected}

        def visit(pid, trail):
            if pid in visiting:
                raise ValueError(f"dependency cycle includes {' -> '.join(trail + [pid])}")
            if pid in visited:
                return
            visiting.add(pid)
            for dep in graph.get(pid, []):
                visit(dep, trail + [pid])
            visiting.remove(pid)
            visited.add(pid)

        for pid in graph:
            try:
                visit(pid, [])
            except ValueError as e:
                rejected[pid] = str(e)
        return rejected

    def discover(self):
        """Scan plugin dirs, validate manifests + graph. Returns (loaded, rejected)."""
        self.plugins, self.rejected = {}, {}
        if not self.dir.exists():
            return [], {}
        manifests = []
        for pdir in sorted(self.dir.iterdir()):
            if not pdir.is_dir():
                continue
            data, err = self._load_manifest(pdir)
            if err:
                # Key by plugin_id when the raw manifest names one, else dir name,
                # so rejected keys are consistent across failure kinds.
                key = pdir.name
                try:
                    raw = json.loads((pdir / "manifest.json").read_text())
                    if isinstance(raw, dict) and raw.get("plugin_id"):
                        key = raw["plugin_id"]
                except Exception:
                    pass
                self.rejected[key] = err
                continue
            if data.get("enabled", True) is False:
                self.rejected[data["plugin_id"]] = "disabled by manifest (enabled: false)"
                continue
            manifests.append((data, pdir))
        graph_rejected = self._validate_graph([m for m, _ in manifests])
        for data, pdir in manifests:
            if data["plugin_id"] in graph_rejected:
                self.rejected[data["plugin_id"]] = graph_rejected[data["plugin_id"]]
                continue
            try:
                mod = self._load_module(data, pdir)
                self.plugins[data["plugin_id"]] = Plugin(data, pdir, mod)
            except Exception as e:
                self.rejected[data["plugin_id"]] = f"load failed: {e}"
        self.core_healthy = True  # core is healthy even with 0 plugins / all rejected
        return list(self.plugins), dict(self.rejected)

    def activate_all(self, configs=None):
        configs = configs or {}
        for pid, plugin in self.plugins.items():
            try:
                plugin.activate(configs.get(pid))
            except Exception as e:
                plugin.status = "failed"
                self.rejected[pid] = f"activation failed: {e}"
        return {pid: p.status for pid, p in self.plugins.items()}

    def invoke(self, capability, **kwargs):
        """Invoke by capability name across active plugins. First provider wins;
        unknown capability = honest error, never a stub success."""
        for plugin in self.plugins.values():
            if plugin.status != "active":
                continue
            caps = getattr(plugin.instance, "capabilities", None) or {}
            if capability in caps:
                return {"plugin": plugin.id, "plugin_version": plugin.version,
                        "capability": capability, "result": plugin.invoke(capability, **kwargs)}
        raise ValueError(f"no active plugin provides {capability!r}")

    def capabilities(self):
        out = {}
        for plugin in self.plugins.values():
            if plugin.status == "active":
                caps = getattr(plugin.instance, "capabilities", None) or {}
                for cap in caps:
                    out[cap] = plugin.id
        return out

    def disable(self, plugin_id):
        """Manifest change equivalent, in-process: stop it, core stays healthy.
        Dependents report degraded (they stay registered, not active)."""
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            raise ValueError(f"unknown plugin {plugin_id!r}")
        plugin.stop()
        plugin.status = "disabled"
        for other in self.plugins.values():
            if other.status != "active":
                continue
            deps = [d["plugin_id"] for d in other.manifest.get("dependencies") or []]
            if plugin_id in deps:
                other.status = "degraded"
        return plugin.status

    def replace(self, plugin_id, new_manifest, new_dir):
        """Replace a plugin without editing core: load the new one, activate it,
        keep the old one until the new one activates, roll back on failure."""
        old = self.plugins.get(plugin_id)
        data, err = self._load_manifest(new_dir)
        if err:
            raise ValueError(f"replacement rejected: {err}")
        if data["plugin_id"] != plugin_id:
            raise ValueError("replacement plugin_id must match")
        try:
            mod = self._load_module(data, new_dir)
            new = Plugin(data, new_dir, mod)
            new.activate()
        except Exception as e:
            raise ValueError(f"replacement failed, old plugin kept: {e}")
        if old is not None:
            old.stop()
        self.plugins[plugin_id] = new
        return new.version

    def reload(self):
        """Rescan manifests. Add / remove / enable / disable / replace by
        manifest change only. Active plugins whose manifest is unchanged
        stay active (no restart of the core, no restart of the plugin)."""
        old_active = {pid: p for pid, p in self.plugins.items() if p.status == "active"}
        loaded, rejected = self.discover()
        for pid, plugin in self.plugins.items():
            old = old_active.get(pid)
            if old is not None and old.manifest == plugin.manifest:
                plugin.instance = old.instance
                plugin.status = "active"
            elif pid not in old_active:
                # Newly added / re-enabled plugin: activate it, fail closed on error.
                try:
                    plugin.activate()
                except Exception as e:
                    plugin.status = "failed"
                    self.rejected[pid] = f"activation failed: {e}"
        # stop plugins that disappeared / were disabled
        for pid, old in old_active.items():
            if pid not in self.plugins:
                old.stop()
        return {"active": [pid for pid, p in self.plugins.items() if p.status == "active"],
                "rejected": dict(self.rejected)}

    def health(self):
        return {"core": "healthy" if self.core_healthy else "failed",
                "core_contract": CORE_CONTRACT,
                "active": [pid for pid, p in self.plugins.items() if p.status == "active"],
                "registered": list(self.plugins),
                "rejected": dict(self.rejected),
                "capabilities": self.capabilities()}

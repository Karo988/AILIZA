from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml


class KillSwitchLevel(str, Enum):
    GLOBAL = "global"
    PROVIDER = "provider"
    MODULE = "module"
    CAPABILITY = "capability"


@dataclass
class KillSwitch:
    """
    In-Memory Kill-Switch mit 4 Ebenen.
    Initialzustand aus YAML — kein DB-Roundtrip beim Halt.
    Audit-Logging: Verantwortung des Aufrufers (Vault-Aufgabe).
    """

    _global: bool = True
    _providers: dict[str, bool] = field(default_factory=dict)
    _modules: dict[str, bool] = field(default_factory=dict)
    _capabilities: dict[str, bool] = field(default_factory=dict)

    # --- Laden ---

    @classmethod
    def load_from_config(cls, path: str | Path) -> "KillSwitch":
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        ks = cls()
        ks._global = cfg.get("global", {}).get("enabled", True)
        ks._providers = {
            k: v.get("enabled", True)
            for k, v in cfg.get("providers", {}).items()
        }
        ks._modules = {
            k: v.get("enabled", True)
            for k, v in cfg.get("modules", {}).items()
        }
        ks._capabilities = {
            k: v.get("enabled", True)
            for k, v in cfg.get("capabilities", {}).items()
        }
        return ks

    # --- Prüfen ---

    def is_allowed(
        self,
        provider: Optional[str] = None,
        module: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> bool:
        """
        Traversiert global → provider → module → capability.
        Erstes False stoppt sofort.
        """
        if not self._global:
            return False
        if provider and not self._providers.get(provider, True):
            return False
        if module and not self._modules.get(module, True):
            return False
        if capability and not self._capabilities.get(capability, True):
            return False
        return True

    # --- Schalten ---

    def halt_global(self) -> None:
        self._global = False

    def halt_provider(self, provider: str) -> None:
        self._providers[provider] = False

    def halt_module(self, module: str) -> None:
        self._modules[module] = False

    def halt_capability(self, capability: str) -> None:
        self._capabilities[capability] = False

    def resume(
        self,
        provider: Optional[str] = None,
        module: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> None:
        """Reaktiviert eine Ebene — Global nur explizit via resume_global()."""
        if provider:
            self._providers[provider] = True
        if module:
            self._modules[module] = True
        if capability:
            self._capabilities[capability] = True

    def resume_global(self) -> None:
        self._global = True

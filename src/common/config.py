from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class AppConfig:
    def __init__(self, data: dict[str, Any], root: Path) -> None:
        self.data = data
        self.root = root

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        config_path = Path(path).resolve()
        with config_path.open("r", encoding="utf-8") as f:
            return cls(json.load(f), config_path.parent)

    def get(self, *keys: str, default: Any = None) -> Any:
        current: Any = self.data
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    def path(self, name: str) -> Path:
        value = self.get("paths", name)
        if not value:
            raise KeyError(f"Missing path setting: {name}")
        path = Path(value)
        if not path.is_absolute():
            path = self.root / path
        return path

    @property
    def proxies(self) -> dict[str, str] | None:
        proxy = self.get("proxy", default={}) or {}
        if not proxy.get("enabled"):
            return None
        proxies = {
            "http": proxy.get("http", ""),
            "https": proxy.get("https", ""),
        }
        return {k: v for k, v in proxies.items() if v}

    def apply_proxy_env(self) -> None:
        proxies = self.proxies
        if not proxies:
            return
        if proxies.get("http"):
            os.environ["HTTP_PROXY"] = proxies["http"]
            os.environ["http_proxy"] = proxies["http"]
        if proxies.get("https"):
            os.environ["HTTPS_PROXY"] = proxies["https"]
            os.environ["https_proxy"] = proxies["https"]


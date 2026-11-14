"""Config loader: agent/config.yaml + env overrides. Single source of truth for tunables."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
# GIGBID_HOME: writable dir for var/ (caches, dbs) when installed as a package (e.g. via uvx)
HOME = Path(os.getenv("GIGBID_HOME", ROOT))


def _load_env_file() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


@lru_cache
def config() -> dict:
    _load_env_file()
    cfg = yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))
    cfg["profile"] = os.getenv("GIGBID_PROFILE", cfg["profile"])
    if os.getenv("GIGBID_RAG_VARIANT"):
        cfg["rag"]["variant"] = os.environ["GIGBID_RAG_VARIANT"]
    if os.getenv("GIGBID_MARKETPLACE"):
        cfg["marketplace"]["adapter"] = os.environ["GIGBID_MARKETPLACE"]
    return cfg


def profile() -> dict:
    cfg = config()
    return {"name": cfg["profile"], **cfg["profiles"][cfg["profile"]]}


@lru_cache
def policy_rules() -> dict:
    cfg = config()
    rules = yaml.safe_load((ROOT / cfg["policy"]["rules_path"]).read_text(encoding="utf-8"))
    rules.update(cfg["policy"].get("overrides") or {})
    return rules


def reload() -> None:
    config.cache_clear()
    policy_rules.cache_clear()

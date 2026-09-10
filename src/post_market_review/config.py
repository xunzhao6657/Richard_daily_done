from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .util import env_path, read_json


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    root: Path
    raw: dict[str, Any]

    @property
    def state_root(self) -> Path:
        return env_path("REVIEW_STATE_ROOT", self.root / ".runtime") or self.root / ".runtime"

    @property
    def ledger_path(self) -> Path:
        return self.state_root / "state" / "review-ledger.sqlite"

    @property
    def wind_cli(self) -> Path:
        default = Path.home() / ".agents" / "skills" / "wind-mcp-skill" / "scripts" / "cli.mjs"
        return env_path("WIND_CLI_PATH", default) or default

    @property
    def report_root(self) -> Path:
        return env_path("REVIEW_REPORT_ROOT", self.root / ".runtime" / "reports") or self.root / ".runtime" / "reports"

    @property
    def morning_root(self) -> Path | None:
        return env_path("MORNING_REPORT_ROOT")

    @property
    def secret_file(self) -> Path:
        default = Path.home() / "AppData" / "Local" / "RichardDailyDone" / "deepseek.key.dpapi"
        return env_path("DEEPSEEK_SECRET_FILE", default) or default


def load_config(path: Path) -> RuntimeConfig:
    value = read_json(path)
    required = {"schema_version", "timezone", "windows_timezone", "mode", "schedule", "data", "llm", "publication"}
    if set(value) != required:
        raise ConfigError(f"RUNTIME_KEYS:missing={sorted(required - set(value))},extra={sorted(set(value) - required)}")
    if value["schema_version"] != "review-runtime.v1":
        raise ConfigError("RUNTIME_SCHEMA")
    if value["timezone"] != "Asia/Shanghai" or value["windows_timezone"] != "China Standard Time":
        raise ConfigError("TIMEZONE")
    if value["mode"] not in {"shadow", "production"}:
        raise ConfigError("MODE")
    schedule = value["schedule"]
    if not schedule["collect_at"] < schedule["freeze_at"] < schedule["llm_deadline"] < schedule["ready_deadline"] < schedule["publish_at"]:
        raise ConfigError("SCHEDULE_ORDER")
    llm = value["llm"]
    if llm["base_url"] != "https://api.deepseek.com" or llm["model"] != "deepseek-v4-flash":
        raise ConfigError("DEEPSEEK_ENDPOINT_OR_MODEL")
    if set(llm.get("accepted_response_models", [])) != {"deepseek-v4-flash", "deepseek-flash"}:
        raise ConfigError("DEEPSEEK_RESPONSE_MODEL_ALLOWLIST")
    if not value["publication"]["local_only"]:
        raise ConfigError("EXTERNAL_DELIVERY_NOT_AUTHORIZED")
    root = path.resolve().parents[1]
    authorization = read_json(root / "config" / "outbound_authorization.json")
    if authorization.get("status") != "AUTHORIZED" or authorization.get("destination") != llm["base_url"]:
        raise ConfigError("OUTBOUND_AUTHORIZATION")
    prohibited = set(authorization.get("prohibited", []))
    required_prohibited = {"provider API credentials", "DeepSeek API credentials", "raw Wind responses", "local filesystem paths"}
    if not required_prohibited.issubset(prohibited):
        raise ConfigError("OUTBOUND_EXCLUSIONS")
    return RuntimeConfig(root, value)


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "runtime.json"

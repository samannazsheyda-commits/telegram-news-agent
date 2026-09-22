from __future__ import annotations

import argparse
import json
import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .builder import BuilderWorkflow, CommandBuilderAdapter
from .config import ProductionConfig
from .e2e import E2ERunner
from .google_translation import GoogleTranslateClient
from .luna import LunaOperator
from .migration import LegacyMigrator
from .openai_client import OpenAIAudioTranscriber, OpenAIResponsesClient
from .observation import ObservationLedger
from .operations import BackupManager, MonitoringService
from .permissions import PermissionGate
from .postgres import PostgresCore
from .publisher import TelegramPublisher
from .queue import RedisJobQueue
from .source_runtime import CollectorRuntime, SourceFetcher
from .telegram import TelegramBotClient
from .translation import TranslationPipeline
from .web import create_app
from .workers import PublishWorker, TranslationWorker


def _required(values: Mapping[str, str], name: str) -> str:
    value = str(values.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class RuntimeEnvironment:
    database_url: str
    redis_url: str
    secret_key: str
    admin_username: str
    admin_password_hash: str
    telegram_bot_token: str
    telegram_chat_id: str
    openai_api_key: str
    openai_model: str
    x_bearer_token: str = ""
    app_root: Path = Path("/opt/bikhabar-vision5")
    data_root: Path = Path("/var/lib/bikhabar/vision5")
    log_root: Path = Path("/var/log/bikhabar/vision5")

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "RuntimeEnvironment":
        base = ProductionConfig.from_mapping(values)
        secret = _required(values, "BIKHABAR_V5_SECRET_KEY")
        if len(secret) < 32:
            raise ValueError("BIKHABAR_V5_SECRET_KEY must be at least 32 characters")
        return cls(
            database_url=base.database_url,
            redis_url=base.redis_url,
            secret_key=secret,
            admin_username=_required(values, "BIKHABAR_V5_ADMIN_USERNAME"),
            admin_password_hash=_required(values, "BIKHABAR_V5_ADMIN_PASSWORD_HASH"),
            telegram_bot_token=_required(values, "BIKHABAR_V5_TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_required(values, "BIKHABAR_V5_TELEGRAM_CHAT_ID"),
            openai_api_key=_required(values, "BIKHABAR_V5_OPENAI_API_KEY"),
            openai_model=_required(values, "BIKHABAR_V5_OPENAI_MODEL"),
            x_bearer_token=str(values.get("BIKHABAR_V5_X_BEARER_TOKEN") or "").strip(),
            app_root=base.app_root,
            data_root=base.data_root,
            log_root=base.log_root,
        )


def _components(values: Mapping[str, str]) -> tuple[RuntimeEnvironment, dict[str, Any]]:
    environment = RuntimeEnvironment.from_mapping(values)
    store = PostgresCore(environment.database_url)
    queue = RedisJobQueue(environment.redis_url)
    google = GoogleTranslateClient()
    model = OpenAIResponsesClient(
        api_key=environment.openai_api_key,
        model=environment.openai_model,
    )
    telegram = TelegramBotClient(
        token=environment.telegram_bot_token,
        chat_id=environment.telegram_chat_id,
    )
    return environment, {
        "store": store,
        "queue": queue,
        "google": google,
        "model": model,
        "telegram": telegram,
    }


def _builder(values: Mapping[str, str], environment: RuntimeEnvironment):
    if not _enabled(values.get("BIKHABAR_V5_BUILDER_ENABLED")):
        return None
    adapter = CommandBuilderAdapter(
        repo_path=environment.app_root / "current",
        test_command=shlex.split(_required(values, "BIKHABAR_V5_BUILDER_TEST_COMMAND")),
        preview_command=shlex.split(_required(values, "BIKHABAR_V5_BUILDER_PREVIEW_COMMAND")),
        deploy_command=shlex.split(_required(values, "BIKHABAR_V5_BUILDER_DEPLOY_COMMAND")),
    )
    gate = PermissionGate(secret=environment.secret_key)
    return BuilderWorkflow(adapter=adapter, permission_gate=gate)


def create_production_panel(environ: Mapping[str, str] | None = None):
    values = environ or os.environ
    environment, parts = _components(values)
    luna = LunaOperator(store=parts["store"], model=parts["model"])
    transcriber = OpenAIAudioTranscriber(api_key=environment.openai_api_key)
    return create_app(
        store=parts["store"],
        job_queue=parts["queue"],
        luna=luna,
        transcriber=transcriber,
        builder=_builder(values, environment),
        config={
            "SECRET_KEY": environment.secret_key,
            "ADMIN_USERNAME": environment.admin_username,
            "ADMIN_PASSWORD_HASH": environment.admin_password_hash,
            "SESSION_COOKIE_SECURE": True,
        },
    )


def _monitor(parts: dict[str, Any]) -> dict[str, Any]:
    def postgres_probe():
        row = parts["store"].connection.execute("SELECT 1 AS ok").fetchone()
        return {"ok": bool(row and int(row["ok"]) == 1), "detail": "reachable"}

    def redis_probe():
        ok = parts["queue"]._redis().ping() is True
        return {"ok": ok, "detail": "reachable" if ok else "ping failed"}

    return MonitoringService(
        store=parts["store"],
        probes={"postgres": postgres_probe, "redis": redis_probe},
        alerter=parts["telegram"],
    ).run()


def main(argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bikhabar_v5.runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in (
        "init-db",
        "collect",
        "translation-worker",
        "publish-worker",
        "monitor",
        "backup",
        "observe",
        "verify-observation",
    ):
        subparsers.add_parser(name)
    migrate = subparsers.add_parser("migrate")
    migrate.add_argument("--legacy-root", default="/opt/bikhabar")
    migrate.add_argument("--dry-run", action="store_true")
    e2e = subparsers.add_parser("e2e")
    e2e.add_argument("--confirm-chat-id", required=True)
    e2e.add_argument("--source-title", required=True)
    e2e.add_argument("--source-body", required=True)
    e2e.add_argument("--source-url", required=True)
    args = parser.parse_args(argv)
    values = environ or os.environ
    environment, parts = _components(values)
    store = parts["store"]

    if args.command == "init-db":
        store.initialize()
        return 0
    if args.command == "collect":
        result = CollectorRuntime(
            store=store,
            queue=parts["queue"],
            fetcher=SourceFetcher(x_bearer_token=environment.x_bearer_token),
        ).run_once()
    elif args.command == "translation-worker":
        TranslationWorker(
            store=store,
            queue=parts["queue"],
            pipeline=TranslationPipeline(google=parts["google"], luna=parts["model"]),
        ).run_forever()
        return 0
    elif args.command == "publish-worker":
        PublishWorker(
            queue=parts["queue"],
            publisher=TelegramPublisher(store=store, telegram=parts["telegram"]),
        ).run_forever()
        return 0
    elif args.command == "monitor":
        result = _monitor(parts)
    elif args.command == "backup":
        result = BackupManager(
            database_url=environment.database_url,
            backup_root=environment.data_root / "backups",
        ).create()
    elif args.command == "observe":
        result = ObservationLedger(
            root=environment.data_root / "evidence", store=store
        ).record()
        result = {"ok": bool(result["healthy"]), "sample": result}
    elif args.command == "verify-observation":
        result = ObservationLedger(
            root=environment.data_root / "evidence", store=store
        ).verify(hours=24)
    elif args.command == "migrate":
        result = LegacyMigrator(legacy_root=args.legacy_root, store=store).run(dry_run=args.dry_run)
    elif args.command == "e2e":
        result = E2ERunner(
            store=store,
            translator=TranslationPipeline(google=parts["google"], luna=parts["model"]),
            publisher=TelegramPublisher(store=store, telegram=parts["telegram"]),
            telegram_chat_id=environment.telegram_chat_id,
            evidence_root=environment.data_root / "evidence",
        ).run(
            confirm_chat_id=args.confirm_chat_id,
            source_title=args.source_title,
            source_body=args.source_body,
            source_url=args.source_url,
        )
    else:  # pragma: no cover
        parser.error("unknown command")
    print(json.dumps(result, ensure_ascii=False, default=str, sort_keys=True))
    return 0 if result.get("ok", result.get("parity_ok", True)) else 1


if __name__ == "__main__":
    raise SystemExit(main())

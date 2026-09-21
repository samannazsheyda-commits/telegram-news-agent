from __future__ import annotations

import pytest


def _valid_env() -> dict[str, str]:
    return {
        "BIKHABAR_V5_DATABASE_URL": "postgresql://bikhabar:secret@127.0.0.1:5432/bikhabar_v5",
        "BIKHABAR_V5_REDIS_URL": "redis://127.0.0.1:6379/5",
    }


def test_v5_production_runtime_is_strictly_isolated_from_legacy():
    from bikhabar_v5.config import ProductionConfig

    cfg = ProductionConfig.from_mapping(_valid_env())

    assert str(cfg.app_root) == "/opt/bikhabar-vision5"
    assert str(cfg.data_root) == "/var/lib/bikhabar/vision5"
    assert str(cfg.log_root) == "/var/log/bikhabar/vision5"
    assert str(cfg.env_file) == "/etc/bikhabar/v5.env"
    assert "/opt/bikhabar/app" not in {str(cfg.app_root), str(cfg.data_root), str(cfg.log_root)}


def test_v5_production_requires_postgresql_and_redis():
    from bikhabar_v5.config import ProductionConfig, RuntimeConfigurationError

    with pytest.raises(RuntimeConfigurationError, match="PostgreSQL"):
        ProductionConfig.from_mapping(
            {
                "BIKHABAR_V5_DATABASE_URL": "sqlite:////var/lib/bikhabar/v5.db",
                "BIKHABAR_V5_REDIS_URL": "redis://127.0.0.1:6379/5",
            }
        )

    with pytest.raises(RuntimeConfigurationError, match="Redis"):
        ProductionConfig.from_mapping(
            {
                "BIKHABAR_V5_DATABASE_URL": "postgresql://127.0.0.1/bikhabar_v5",
                "BIKHABAR_V5_REDIS_URL": "",
            }
        )


def test_v5_production_never_silently_reads_legacy_credentials():
    from bikhabar_v5.config import ProductionConfig, RuntimeConfigurationError

    with pytest.raises(RuntimeConfigurationError):
        ProductionConfig.from_mapping(
            {
                "DATABASE_URL": "postgresql://legacy/legacy",
                "REDIS_URL": "redis://legacy/0",
            }
        )

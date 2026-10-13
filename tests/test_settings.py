"""Unit tests for configuration management and settings."""

from pathlib import Path
from unittest.mock import patch

from rdr_transit.settings import AppConfig, load_config, save_config


def test_app_config_defaults():
    cfg = AppConfig()
    assert cfg.transfer_port == 17116
    assert cfg.broadcast_port == 56780
    assert cfg.default_parallel == 4
    assert cfg.verify_checksum is True


def test_config_save_and_load(tmp_path):
    test_cfg_file = tmp_path / "sub" / "config.json"
    test_cfg_dir = tmp_path / "sub"

    with patch("rdr_transit.settings.CONFIG_FILE", test_cfg_file), \
         patch("rdr_transit.settings.CONFIG_DIR", test_cfg_dir):
        cfg = AppConfig(
            device_name="test-box",
            transfer_port=19999,
            default_parallel=8,
            beacon_interval=2.5,
        )
        save_config(cfg)
        assert test_cfg_file.exists()

        loaded = load_config()
        assert loaded.device_name == "test-box"
        assert loaded.transfer_port == 19999
        assert loaded.default_parallel == 8
        assert loaded.beacon_interval == 2.5

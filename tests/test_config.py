from pathlib import Path

import pytest

from dn_home.core.config import ConfigError, load_config


VALID_CONFIG = """
house:
  resident_name: David
voice:
  engine: edge
  language: pt-PT
  default_voice: pt-PT-DuarteNeural
speaker:
  provider: cast
  name: Bedroom
  host: 192.168.20.40
  volume: 35
network: {}
http: {}
logging:
  file: logs/test.log
"""


def test_load_config_resolves_values(tmp_path: Path) -> None:
    path = tmp_path / "config" / "config.yaml"
    path.parent.mkdir()
    path.write_text(VALID_CONFIG, encoding="utf-8")

    config = load_config(path)

    assert config.resident_name == "David"
    assert config.speaker.host == "192.168.20.40"
    assert config.speaker.volume == 35
    assert config.network.lan_ip is None
    assert config.http.port == 8765
    assert config.logging.file == tmp_path / "logs" / "test.log"


def test_rejects_out_of_range_volume(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(VALID_CONFIG.replace("volume: 35", "volume: 101"), encoding="utf-8")

    with pytest.raises(ConfigError, match="speaker.volume"):
        load_config(path)


def test_requires_cast_identity(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    text = VALID_CONFIG.replace("name: Bedroom", 'name: ""').replace(
        "host: 192.168.20.40", 'host: ""'
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError, match="speaker.name or speaker.host"):
        load_config(path)


def test_rejects_ephemeral_media_port(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(VALID_CONFIG.replace("http: {}", "http:\n  port: 0"), encoding="utf-8")

    with pytest.raises(ConfigError, match="http.port"):
        load_config(path)

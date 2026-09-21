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
transit:
  line:
    name: RER A
    id: IDFM:C01742
    code: A
    commercial_mode: RER
  origin:
    name: Noisy-le-Grand - Mont d'Est
    stop_id: IDFM:monomodalStopPlace:474082
    navitia_id: stop_area:IDFM:412697
  destinations:
    work:
      name: Lognes
      stop_id: IDFM:monomodalStopPlace:43152
      navitia_id: stop_area:IDFM:68123
    paris:
      name: Nation
      stop_id: IDFM:monomodalStopPlace:473875
      navitia_id: stop_area:IDFM:71673
"""


def test_load_config_resolves_values(tmp_path: Path) -> None:
    path = tmp_path / "config" / "config.yaml"
    path.parent.mkdir()
    path.write_text(VALID_CONFIG, encoding="utf-8")

    config = load_config(path)

    assert config.resident_name == "David"
    assert config.speaker.host == "192.168.20.40"
    assert config.speaker.manage_volume is False
    assert config.speaker.volume == 35
    assert config.voice.rate == "+0%"
    assert config.voice.pitch == "+0Hz"
    assert config.voice.tts_volume == "+0%"
    assert config.network.lan_ip is None
    assert config.http.port == 8765
    assert config.audio_input.device == "default"
    assert config.wake_word.engine == "openwakeword"
    assert config.stt.language == "pt"
    assert config.transit.origin.stop_id == "IDFM:monomodalStopPlace:474082"
    assert config.transit.destinations["work"].stop_id == "IDFM:monomodalStopPlace:43152"
    assert config.transit.destinations["paris"].stop_id == "IDFM:monomodalStopPlace:473875"
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


def test_loads_valid_voice_prosody(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    text = VALID_CONFIG.replace(
        "  default_voice: pt-PT-DuarteNeural",
        '  default_voice: pt-PT-DuarteNeural\n  rate: "+8%"\n  pitch: "-5Hz"',
    )
    path.write_text(text, encoding="utf-8")

    config = load_config(path)

    assert config.voice.rate == "+8%"
    assert config.voice.pitch == "-5Hz"


@pytest.mark.parametrize(
    ("setting", "value", "error_name"),
    (
        ("rate", "8%", "voice.rate"),
        ("pitch", "-5", "voice.pitch"),
        ("tts_volume", "0%", "voice.tts_volume"),
    ),
)
def test_rejects_invalid_voice_prosody(
    tmp_path: Path, setting: str, value: str, error_name: str
) -> None:
    path = tmp_path / "config.yaml"
    text = VALID_CONFIG.replace(
        "  default_voice: pt-PT-DuarteNeural",
        f'  default_voice: pt-PT-DuarteNeural\n  {setting}: "{value}"',
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ConfigError, match=error_name):
        load_config(path)


def test_can_enable_automatic_cast_volume_management(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    text = VALID_CONFIG.replace(
        "  volume: 35", "  manage_volume: true\n  volume: 35"
    )
    path.write_text(text, encoding="utf-8")

    config = load_config(path)

    assert config.speaker.manage_volume is True

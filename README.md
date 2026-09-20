# DN Home

DN Home is a local-first, modular home assistant for Raspberry Pi 5. Phase 1
proves one deliberately small path:

```text
text -> TTS -> temporary private HTTP server -> Google Cast -> Google Nest
```

The complete requirements and safety constraints live in `PROJECT_SPEC.md`.

## Phase 1 setup

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp config/config.example.yaml config/config.yaml
```

Set `speaker.name` and `speaker.host` in the local `config/config.yaml`. This
file is ignored by Git. IP addresses and network interfaces are never embedded
in source code. `http.port` selects the dedicated TCP port used only while the
Nest fetches generated media; its initial value is `8765`.

## Commands

List Portuguese voices:

```bash
python -m dn_home voices
```

Run read-only diagnostics without playing audio:

```bash
python -m dn_home doctor
```

Speak through the configured Nest:

```bash
python -m dn_home speak "Bem-vindo a casa, David."
python -m dn_home speak --voice pt-PT-DuarteNeural --volume 35 \
  "Olá David. Esta é a voz da tua casa."
python -m dn_home speak --voice pt-PT-DuarteNeural --rate "+8%" \
  --pitch=-5Hz --volume 55 "Bem-vindo a casa David."
```

`--rate` uses a signed percentage and `--pitch` uses signed Hz. If omitted,
they default to `voice.rate` and `voice.pitch` in the YAML configuration. Nest
volume is separate from TTS prosody.

Use `--no-restore-volume` if the requested volume should remain configured on
the Nest after playback. By default the value comes from
`speaker.restore_previous_volume`.

## Networking and privacy

DN Home determines the LAN source address from the route to the configured
Nest unless `network.lan_interface` or `network.lan_ip` is explicitly set. It
refuses wildcard, loopback, public, and common VPN interface addresses for the
temporary media server.

The HTTP server binds only to the selected LAN address and configured dedicated
port. It serves one exact, randomly named file, exposes no directory listing,
and shuts down after playback or timeout. Generated audio is deleted in all
success and error paths.

No paid API, password, token, network reconfiguration, or systemd service is
used in Phase 1. Edge TTS requires Internet access; a local Piper adapter is a
planned fallback but is not installed yet.

## Tests

```bash
python -m pytest
```

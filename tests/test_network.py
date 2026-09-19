import pytest

from dn_home.core import network


def test_selects_configured_lan_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(network, "_resolve_ipv4", lambda host, port: "192.168.20.40")
    monkeypatch.setattr(network, "_interface_for_ip", lambda address: "br0")

    result = network.select_lan_address(
        "nest.local",
        8009,
        explicit_ip="192.168.20.10",
    )

    assert result.local_ip == "192.168.20.10"
    assert result.interface == "br0"
    assert result.method == "configured-address"


def test_selects_configured_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(network, "_resolve_ipv4", lambda host, port: "192.168.50.25")
    monkeypatch.setattr(
        network,
        "_interface_ipv4",
        lambda interface: "192.168.50.1" if interface == "lan0" else None,
    )

    result = network.select_lan_address(
        "nest.local",
        8009,
        explicit_interface="lan0",
    )

    assert result.local_ip == "192.168.50.1"
    assert result.interface == "lan0"


def test_rejects_vpn_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(network, "_resolve_ipv4", lambda host, port: "192.168.20.40")
    monkeypatch.setattr(network, "_interface_for_ip", lambda address: "tailscale0")

    with pytest.raises(network.NetworkSelectionError, match="VPN interface"):
        network.select_lan_address(
            "nest.local",
            8009,
            explicit_ip="10.100.0.10",
        )


def test_rejects_public_bind_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(network, "_resolve_ipv4", lambda host, port: "192.168.20.40")
    monkeypatch.setattr(network, "_interface_for_ip", lambda address: "eth9")

    with pytest.raises(network.NetworkSelectionError, match="non-private"):
        network.select_lan_address(
            "nest.local",
            8009,
            explicit_ip="8.8.8.8",
        )


def test_rejects_target_outside_private_lan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(network, "_resolve_ipv4", lambda host, port: "8.8.4.4")

    with pytest.raises(network.NetworkSelectionError, match="outside the private LAN"):
        network.select_lan_address("not-a-nest.example", 8009)

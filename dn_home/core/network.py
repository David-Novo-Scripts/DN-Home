"""Select the safe LAN source address used to serve Cast media."""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import ipaddress
import logging
import socket
import struct


LOGGER = logging.getLogger(__name__)
SIOCGIFADDR = 0x8915
VPN_PREFIXES = ("tailscale", "tun", "tap", "wg", "vpn", "ppp")


class NetworkSelectionError(RuntimeError):
    """Raised when no safe LAN address can be selected."""


@dataclass(frozen=True, slots=True)
class NetworkSelection:
    local_ip: str
    interface: str
    target_ip: str
    method: str


def _interface_ipv4(interface: str) -> str | None:
    request = struct.pack("256s", interface.encode("utf-8")[:15])
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            response = fcntl.ioctl(sock.fileno(), SIOCGIFADDR, request)
        except OSError:
            return None
    return socket.inet_ntoa(response[20:24])


def _interface_for_ip(local_ip: str) -> str | None:
    for _, interface in socket.if_nameindex():
        if _interface_ipv4(interface) == local_ip:
            return interface
    return None


def _resolve_ipv4(host: str, port: int) -> str:
    try:
        addresses = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise NetworkSelectionError(f"Unable to resolve speaker host '{host}': {error}") from error
    if not addresses:
        raise NetworkSelectionError(f"No IPv4 address found for speaker host '{host}'")
    return addresses[0][4][0]


def _validate_lan_address(local_ip: str, interface: str) -> None:
    try:
        address = ipaddress.ip_address(local_ip)
    except ValueError as error:
        raise NetworkSelectionError(f"Invalid LAN address: {local_ip}") from error
    if address.version != 4 or address.is_unspecified or address.is_loopback or address.is_multicast:
        raise NetworkSelectionError(f"Unsafe HTTP bind address: {local_ip}")
    if not address.is_private:
        raise NetworkSelectionError(
            f"Refusing to advertise non-private address {local_ip}; configure the LAN explicitly"
        )
    if interface.lower().startswith(VPN_PREFIXES):
        raise NetworkSelectionError(
            f"Refusing to advertise VPN interface '{interface}' to the Cast device"
        )


def _validate_target_address(target_ip: str) -> None:
    address = ipaddress.ip_address(target_ip)
    if (
        address.version != 4
        or address.is_unspecified
        or address.is_loopback
        or address.is_multicast
        or not address.is_private
    ):
        raise NetworkSelectionError(
            f"Refusing Cast target outside the private LAN: {target_ip}"
        )


def select_lan_address(
    target_host: str,
    target_port: int,
    *,
    explicit_ip: str | None = None,
    explicit_interface: str | None = None,
) -> NetworkSelection:
    """Select an IPv4 source using explicit LAN config or the target route."""

    target_ip = _resolve_ipv4(target_host, target_port)
    _validate_target_address(target_ip)

    if explicit_interface:
        interface_ip = _interface_ipv4(explicit_interface)
        if not interface_ip:
            raise NetworkSelectionError(
                f"LAN interface '{explicit_interface}' has no usable IPv4 address"
            )
        if explicit_ip and explicit_ip != interface_ip:
            raise NetworkSelectionError(
                f"Configured LAN IP {explicit_ip} does not belong to {explicit_interface}"
            )
        local_ip = explicit_ip or interface_ip
        interface = explicit_interface
        method = "configured-interface"
    elif explicit_ip:
        local_ip = explicit_ip
        interface = _interface_for_ip(local_ip) or "unknown"
        if interface == "unknown":
            raise NetworkSelectionError(f"Configured LAN IP {local_ip} is not assigned locally")
        method = "configured-address"
    else:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_socket:
                route_socket.connect((target_ip, target_port))
                local_ip = route_socket.getsockname()[0]
        except OSError as error:
            raise NetworkSelectionError(
                f"Unable to determine route to Cast device {target_ip}: {error}"
            ) from error
        interface = _interface_for_ip(local_ip) or "unknown"
        if interface == "unknown":
            raise NetworkSelectionError(f"Could not identify the interface for {local_ip}")
        method = "route-to-target"

    _validate_lan_address(local_ip, interface)
    selection = NetworkSelection(local_ip, interface, target_ip, method)
    LOGGER.debug(
        "event=network.route_selected target=%s local_ip=%s interface=%s method=%s",
        selection.target_ip,
        selection.local_ip,
        selection.interface,
        selection.method,
    )
    return selection

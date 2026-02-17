# Changelog

## 0.5.0

### Breaking changes
- Removed deprecated `loop` parameter from `EmulatedRokuServer` and `EmulatedRokuDiscoveryProtocol`. Uses `asyncio.get_running_loop()` / `asyncio.create_task()` directly.
- Requires Python 3.14+.

### Fixed
- Fixed `MULTICAST_TTL` constant typo (was `MUTLICAST_TTL`).
- Fixed MX header parsing in SSDP discovery — now handles multi-digit values, missing MX header, and malformed values without crashing.
- Fixed `build_custom_apps` dropping text after a second colon in app names (e.g. `1:My App: Extended`).
- Fixed `build_custom_apps` return type annotation (`str | None`).
- Fixed `get_local_ip` socket leak if `socket.socket()` constructor fails.
- Fixed `advertise_port=0` being treated as `None` due to falsy check.

### Added
- Test suite with pytest + pytest-aiohttp (47 tests).
- GitHub Actions CI workflow for tests.
- `py.typed` marker for PEP 561.
- `[test]` optional dependency group.

### Removed
- Removed legacy `setup.py` and `setup.cfg` (replaced by `pyproject.toml`).

## 0.4.0

- Added support for custom applications list.

## 0.3.0

- Initial public release.

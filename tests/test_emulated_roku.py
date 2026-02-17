"""Tests for emulated_roku."""
import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from emulated_roku import (
    APP_PLACEHOLDER_ICON,
    APPS_TEMPLATE_DEFAULT,
    EmulatedRokuCommandHandler,
    EmulatedRokuDiscoveryProtocol,
    EmulatedRokuServer,
    build_custom_apps,
    get_local_ip,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def handler():
    """Create a mock command handler that tracks calls."""
    h = MagicMock(spec=EmulatedRokuCommandHandler)
    return h


@pytest.fixture
def server(handler):
    """Create an EmulatedRokuServer instance (not started)."""
    return EmulatedRokuServer(
        handler=handler,
        roku_usn="test-usn",
        host_ip="127.0.0.1",
        listen_port=8060,
    )


@pytest.fixture
async def client(server):
    """Create an aiohttp TestClient wired to the server's app."""
    runner = await server._setup_app()
    app = runner.app
    # Shut down the runner we just created — TestServer manages its own.
    await runner.cleanup()

    async with TestClient(TestServer(app)) as tc:
        yield tc


def _host_header(server):
    """Return a Host header value the middleware will accept."""
    return {"Host": f"{server.host_ip}:{server.listen_port}"}


# ---------------------------------------------------------------------------
# 1. Server initialisation
# ---------------------------------------------------------------------------

class TestServerInit:
    def test_defaults(self, handler):
        s = EmulatedRokuServer(
            handler=handler,
            roku_usn="my-usn",
            host_ip="192.168.1.10",
            listen_port=8060,
        )
        assert s.advertise_ip == "192.168.1.10"
        assert s.advertise_port == 8060
        assert s.roku_usn == "my-usn"

    def test_custom_advertise(self, handler):
        s = EmulatedRokuServer(
            handler=handler,
            roku_usn="my-usn",
            host_ip="192.168.1.10",
            listen_port=8060,
            advertise_ip="10.0.0.1",
            advertise_port=9090,
        )
        assert s.advertise_ip == "10.0.0.1"
        assert s.advertise_port == 9090

    def test_bind_multicast_default_non_windows(self, handler):
        with patch("emulated_roku.osname", "posix"):
            s = EmulatedRokuServer(
                handler=handler, roku_usn="u", host_ip="127.0.0.1",
                listen_port=8060,
            )
            assert s.bind_multicast is True

    def test_bind_multicast_default_windows(self, handler):
        with patch("emulated_roku.osname", "nt"):
            s = EmulatedRokuServer(
                handler=handler, roku_usn="u", host_ip="127.0.0.1",
                listen_port=8060,
            )
            assert s.bind_multicast is False

    def test_bind_multicast_explicit(self, handler):
        s = EmulatedRokuServer(
            handler=handler, roku_usn="u", host_ip="127.0.0.1",
            listen_port=8060, bind_multicast=True,
        )
        assert s.bind_multicast is True

    def test_custom_apps_stored(self, handler):
        s = EmulatedRokuServer(
            handler=handler, roku_usn="u", host_ip="127.0.0.1",
            listen_port=8060, custom_apps="1:App One,2:App Two",
        )
        assert s.custom_apps is not None
        assert "App One" in s.custom_apps

    def test_no_loop_parameter(self, handler):
        """EmulatedRokuServer does not accept a loop parameter."""
        import inspect
        sig = inspect.signature(EmulatedRokuServer.__init__)
        assert "loop" not in sig.parameters


# ---------------------------------------------------------------------------
# 2. Server lifecycle
# ---------------------------------------------------------------------------

class TestServerLifecycle:
    @pytest.mark.parametrize(
        "bind_multicast, expected_bind",
        [
            (True, ("", 1900)),
            (False, ("127.0.0.1", 1900)),
        ],
    )
    async def test_start_binds_expected_address(
        self, handler, bind_multicast, expected_bind
    ):
        s = EmulatedRokuServer(
            handler=handler,
            roku_usn="u",
            host_ip="127.0.0.1",
            listen_port=8060,
            bind_multicast=bind_multicast,
        )

        mock_runner = MagicMock()
        mock_site = MagicMock()
        mock_site.start = AsyncMock()
        mock_socket = MagicMock()
        mock_loop = MagicMock()
        mock_transport = MagicMock()
        mock_proto = MagicMock()
        mock_loop.create_datagram_endpoint = AsyncMock(
            return_value=(mock_transport, mock_proto)
        )

        with (
            patch.object(s, "_setup_app", AsyncMock(return_value=mock_runner)),
            patch("emulated_roku.web.TCPSite", return_value=mock_site),
            patch("emulated_roku.socket.socket", return_value=mock_socket),
            patch("emulated_roku.asyncio.get_running_loop", return_value=mock_loop),
        ):
            await s.start()

        mock_site.start.assert_awaited_once()
        mock_socket.bind.assert_called_once_with(expected_bind)
        mock_loop.create_datagram_endpoint.assert_awaited_once()
        assert s.api_runner is mock_runner
        assert s.discovery_proto is mock_proto

    async def test_close_cleans_up_runner_and_discovery(self, handler):
        s = EmulatedRokuServer(
            handler=handler,
            roku_usn="u",
            host_ip="127.0.0.1",
            listen_port=8060,
        )
        discovery = MagicMock()
        runner = MagicMock()
        runner.cleanup = AsyncMock()
        s.discovery_proto = discovery
        s.api_runner = runner

        await s.close()

        discovery.close.assert_called_once()
        runner.cleanup.assert_awaited_once()
        assert s.discovery_proto is None
        assert s.api_runner is None


# ---------------------------------------------------------------------------
# 3. HTTP API handlers
# ---------------------------------------------------------------------------

class TestHTTPHandlers:
    @pytest.fixture(autouse=True)
    async def _setup(self, client, server):
        self.client = client
        self.server = server
        self.headers = _host_header(server)

    async def test_root_returns_xml(self):
        resp = await self.client.get("/", headers=self.headers)
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "text/xml"
        body = await resp.text()
        assert "test-usn" in body
        assert "urn:roku-com:device:player:1-0" in body

    async def test_query_apps_default(self):
        resp = await self.client.get("/query/apps", headers=self.headers)
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "text/xml"
        body = await resp.text()
        assert body == APPS_TEMPLATE_DEFAULT

    async def test_query_apps_custom(self, handler):
        custom_server = EmulatedRokuServer(
            handler=handler, roku_usn="test-usn",
            host_ip="127.0.0.1", listen_port=8060,
            custom_apps="100:Netflix,200:YouTube",
        )
        runner = await custom_server._setup_app()
        await runner.cleanup()
        async with TestClient(TestServer(runner.app)) as tc:
            headers = _host_header(custom_server)
            resp = await tc.get("/query/apps", headers=headers)
            assert resp.status == 200
            body = await resp.text()
            assert "Netflix" in body
            assert "YouTube" in body

    async def test_query_active_app(self):
        resp = await self.client.get("/query/active-app", headers=self.headers)
        assert resp.status == 200
        body = await resp.text()
        assert "<app>Roku</app>" in body

    async def test_query_icon(self):
        resp = await self.client.get("/query/icon/1", headers=self.headers)
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "image/png"
        body = await resp.read()
        assert body == APP_PLACEHOLDER_ICON

    async def test_query_device_info(self):
        resp = await self.client.get("/query/device-info", headers=self.headers)
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "text/xml"
        body = await resp.text()
        assert "test-usn" in body
        assert "<model-name>Roku 4</model-name>" in body

    async def test_keypress(self):
        resp = await self.client.post("/keypress/Home", headers=self.headers)
        assert resp.status == 200
        self.server.handler.on_keypress.assert_called_once_with("test-usn", "Home")

    async def test_keydown(self):
        resp = await self.client.post("/keydown/Left", headers=self.headers)
        assert resp.status == 200
        self.server.handler.on_keydown.assert_called_once_with("test-usn", "Left")

    async def test_keyup(self):
        resp = await self.client.post("/keyup/Right", headers=self.headers)
        assert resp.status == 200
        self.server.handler.on_keyup.assert_called_once_with("test-usn", "Right")

    async def test_launch(self):
        resp = await self.client.post("/launch/12345", headers=self.headers)
        assert resp.status == 200
        self.server.handler.launch.assert_called_once_with("test-usn", "12345")

    async def test_input(self):
        resp = await self.client.post("/input", headers=self.headers)
        assert resp.status == 200

    async def test_search(self):
        resp = await self.client.post("/search", headers=self.headers)
        assert resp.status == 200


# ---------------------------------------------------------------------------
# 3. Command handler callbacks
# ---------------------------------------------------------------------------

class TestCommandHandler:
    def test_subclass_callbacks(self):
        calls = []

        class MyHandler(EmulatedRokuCommandHandler):
            def on_keypress(self, roku_usn, key):
                calls.append(("keypress", roku_usn, key))

            def on_keydown(self, roku_usn, key):
                calls.append(("keydown", roku_usn, key))

            def on_keyup(self, roku_usn, key):
                calls.append(("keyup", roku_usn, key))

            def launch(self, roku_usn, app_id):
                calls.append(("launch", roku_usn, app_id))

        h = MyHandler()
        h.on_keypress("usn1", "Home")
        h.on_keydown("usn1", "Left")
        h.on_keyup("usn1", "Right")
        h.launch("usn1", "99")

        assert calls == [
            ("keypress", "usn1", "Home"),
            ("keydown", "usn1", "Left"),
            ("keyup", "usn1", "Right"),
            ("launch", "usn1", "99"),
        ]

    def test_base_handler_noop(self):
        """Base handler methods don't raise."""
        h = EmulatedRokuCommandHandler()
        h.on_keypress("u", "k")
        h.on_keydown("u", "k")
        h.on_keyup("u", "k")
        h.launch("u", "a")


# ---------------------------------------------------------------------------
# 5. Host/IP middleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    @pytest.fixture(autouse=True)
    async def _setup(self, client, server):
        self.client = client
        self.server = server

    async def test_allowed_host(self):
        resp = await self.client.get(
            "/", headers={"Host": self.server.host_ip}
        )
        assert resp.status == 200

    async def test_allowed_host_with_port(self):
        resp = await self.client.get(
            "/", headers={"Host": f"{self.server.host_ip}:{self.server.listen_port}"}
        )
        assert resp.status == 200

    async def test_rejected_host(self):
        resp = await self.client.get(
            "/", headers={"Host": "evil.example.com"}
        )
        assert resp.status == 403

    async def test_rejected_non_local_remote(self, server):
        request = MagicMock()
        request.host = f"{server.host_ip}:{server.listen_port}"
        request.remote = "8.8.8.8"
        handler = AsyncMock()

        with pytest.raises(web.HTTPForbidden):
            await server._check_remote_and_host_ip(request, handler)

        handler.assert_not_awaited()


# ---------------------------------------------------------------------------
# 6. Discovery protocol
# ---------------------------------------------------------------------------

class TestDiscoveryProtocol:
    def test_no_loop_parameter(self):
        import inspect
        sig = inspect.signature(EmulatedRokuDiscoveryProtocol.__init__)
        assert "loop" not in sig.parameters

    def test_construction(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="192.168.1.1", roku_usn="my-usn",
            advertise_ip="192.168.1.1", advertise_port=8060,
        )
        assert proto.host_ip == "192.168.1.1"
        assert proto.roku_usn == "my-usn"
        assert proto.notify_task is None
        assert proto.transport is None

    async def test_connection_made_schedules_notify(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        transport = MagicMock()
        transport.is_closing.return_value = False

        proto.connection_made(transport)

        assert proto.transport is transport
        assert proto.notify_task is not None
        assert isinstance(proto.notify_task, asyncio.Task)

        # Clean up the task
        proto.close()

    async def test_datagram_received_msearch(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        transport = MagicMock()
        transport.is_closing.return_value = False
        proto.transport = transport

        msearch = (
            "M-SEARCH * HTTP/1.1\r\n"
            "HOST: 239.255.255.250:1900\r\n"
            "MAN: \"ssdp:discover\"\r\n"
            "MX: 3\r\n"
            "ST: roku:ecp\r\n"
            "\r\n"
        ).encode()

        with patch("emulated_roku.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value = MagicMock()
            proto.datagram_received(msearch, ("192.168.1.50", 12345))
            mock_loop.return_value.call_later.assert_called_once()

    async def test_datagram_received_non_msearch_ignored(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        transport = MagicMock()
        transport.is_closing.return_value = False
        proto.transport = transport

        data = b"HTTP/1.1 200 OK\r\nSomething\r\n\r\n"

        with patch("emulated_roku.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value = MagicMock()
            proto.datagram_received(data, ("192.168.1.50", 12345))
            mock_loop.return_value.call_later.assert_not_called()

    async def test_datagram_received_msearch_without_mx(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        transport = MagicMock()
        transport.is_closing.return_value = False
        proto.transport = transport

        msearch = (
            "M-SEARCH * HTTP/1.1\r\n"
            "HOST: 239.255.255.250:1900\r\n"
            "MAN: \"ssdp:discover\"\r\n"
            "ST: roku:ecp\r\n"
            "\r\n"
        ).encode()

        with patch("emulated_roku.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value = MagicMock()
            proto.datagram_received(msearch, ("192.168.1.50", 12345))
            mock_loop.return_value.call_later.assert_called_once()

    async def test_datagram_received_msearch_with_malformed_mx(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        transport = MagicMock()
        transport.is_closing.return_value = False
        proto.transport = transport

        msearch = (
            "M-SEARCH * HTTP/1.1\r\n"
            "HOST: 239.255.255.250:1900\r\n"
            "MAN: \"ssdp:discover\"\r\n"
            "MX: x\r\n"
            "ST: roku:ecp\r\n"
            "\r\n"
        ).encode()

        with patch("emulated_roku.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value = MagicMock()
            proto.datagram_received(msearch, ("192.168.1.50", 12345))
            mock_loop.return_value.call_later.assert_called_once()

    async def test_connection_lost_closes_protocol(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        proto.close = MagicMock()

        proto.connection_lost(None)

        proto.close.assert_called_once()

    async def test_multicast_notify_sends_broadcast(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        transport = MagicMock()
        transport.is_closing.side_effect = [False, True]
        proto.transport = transport

        with patch("emulated_roku.sleep", AsyncMock()):
            await proto._multicast_notify()

        transport.sendto.assert_called_once()

    def test_multicast_reply_sends_to_requester(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        transport = MagicMock()
        transport.is_closing.return_value = False
        proto.transport = transport

        proto._multicast_reply("M-SEARCH * HTTP/1.1", ("192.168.1.50", 12345))

        transport.sendto.assert_called_once()

    def test_multicast_reply_ignored_when_transport_closing(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        transport = MagicMock()
        transport.is_closing.return_value = True
        proto.transport = transport

        proto._multicast_reply("M-SEARCH * HTTP/1.1", ("192.168.1.50", 12345))

        transport.sendto.assert_not_called()

    async def test_close_cancels_notify(self):
        proto = EmulatedRokuDiscoveryProtocol(
            host_ip="127.0.0.1", roku_usn="u",
            advertise_ip="127.0.0.1", advertise_port=8060,
        )
        transport = MagicMock()
        transport.is_closing.return_value = False

        proto.connection_made(transport)
        task = proto.notify_task

        proto.close()

        assert proto.notify_task is None
        assert proto.transport is None
        # Let cancellation propagate through the event loop
        await asyncio.sleep(0)
        assert task.cancelled()
        transport.close.assert_called_once()


# ---------------------------------------------------------------------------
# 7. Utility functions
# ---------------------------------------------------------------------------

class TestUtilities:
    def test_build_custom_apps_valid(self):
        result = build_custom_apps("1:App One,2:App Two")
        assert result is not None
        assert "App One" in result
        assert "App Two" in result
        assert "<apps>" in result

    def test_build_custom_apps_newline_separated(self):
        result = build_custom_apps("1:App One\n2:App Two")
        assert result is not None
        assert "App One" in result
        assert "App Two" in result

    def test_build_custom_apps_invalid(self):
        result = build_custom_apps("invalid_no_colon")
        assert result is None

    def test_build_custom_apps_mixed(self):
        result = build_custom_apps("1:Valid,invalid,2:Also Valid")
        assert result is not None
        assert "Valid" in result
        assert "Also Valid" in result

    def test_get_local_ip_returns_string(self):
        ip = get_local_ip()
        assert isinstance(ip, str)
        assert len(ip) > 0

    def test_get_local_ip_fallback_to_hostname_resolution(self):
        with (
            patch("emulated_roku.socket.socket", side_effect=socket.error),
            patch("emulated_roku.socket.gethostbyname", return_value="192.168.1.42"),
            patch("emulated_roku.socket.gethostname", return_value="host"),
        ):
            ip = get_local_ip()
        assert ip == "192.168.1.42"

    def test_get_local_ip_fallback_to_loopback(self):
        with (
            patch("emulated_roku.socket.socket", side_effect=socket.error),
            patch("emulated_roku.socket.gethostbyname", side_effect=socket.gaierror),
        ):
            ip = get_local_ip()
        assert ip == "127.0.0.1"

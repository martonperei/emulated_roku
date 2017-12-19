"""Emulated Roku library."""
import asyncio
from functools import partial
import logging
import os
import random
import socket
import uuid

from aiohttp import web
import shortuuid

_LOGGER = logging.getLogger(__name__)

USN_GENERATOR = shortuuid.ShortUUID()

ROKU_INFO_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" ?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
    <specVersion>
        <major>1</major>
        <minor>0</minor>
    </specVersion>
    <device>
    <deviceType>urn:roku-com:device:player:1-0</deviceType>
    <friendlyName>Emulated Roku {usn}</friendlyName>
    <manufacturer>Emulated Roku</manufacturer>
    <manufacturerURL>http://www.roku.com/</manufacturerURL>
    <modelDescription>Emulated Roku</modelDescription>
    <modelName>Emulated Roku 4</modelName>
    <modelNumber>4400x</modelNumber>
    <modelURL>http://www.roku.com/</modelURL>
    <serialNumber>{usn}</serialNumber>
    <UDN>uuid:{uuid}</UDN>
    <serviceList>
        <service>
            <serviceType>urn:roku-com:service:ecp:1</serviceType>
            <serviceId>urn:roku-com:serviceId:ecp1-0</serviceId>
            <controlURL/>
            <eventSubURL/>
            <SCPDURL>ecp_SCPD.xml</SCPDURL>
        </service>
    </serviceList>
    </device>
</root>"""

ROKU_DEVICE_INFO_TEMPLATE = """<device-info>
    <udn>{uuid}</udn>
    <serial-number>{usn}</serial-number>
    <device-id>{usn}</device-id>
    <vendor-name>Emulated Roku</vendor-name>
    <model-number>4400X</model-number>
    <model-name>Emulated Roku 4</model-name>
    <model-region>US</model-region>
    <supports-ethernet>true</supports-ethernet>
    <wifi-mac>b0:a7:37:96:4d:fb</wifi-mac>
    <ethernet-mac>b0:a7:37:96:4d:fa</ethernet-mac>
    <network-type>ethernet</network-type>
    <user-device-name>Emulated Roku {usn}</user-device-name>
    <software-version>7.5.0</software-version>
    <software-build>09021</software-build>
    <secure-device>true</secure-device>
    <language>en</language>
    <country>US</country>
    <locale>en_US</locale>
    <time-zone>US/Pacific</time-zone>
    <time-zone-offset>-480</time-zone-offset>
    <power-mode>PowerOn</power-mode>
    <supports-suspend>false</supports-suspend>
    <supports-find-remote>false</supports-find-remote>
    <supports-audio-guide>false</supports-audio-guide>
    <developer-enabled>true</developer-enabled>
    <keyed-developer-id>70f6ed9c90cf60718a26f3a7c3e5af1c3ec29558</keyed-developer-id>
    <search-enabled>true</search-enabled>
    <voice-search-enabled>true</voice-search-enabled>
    <notifications-enabled>true</notifications-enabled>
    <notifications-first-use>false</notifications-first-use>
    <supports-private-listening>false</supports-private-listening>
    <headphones-connected>false</headphones-connected>
</device-info>"""

APPS_TEMPLATE = """<apps>
    <app id="1" version="1.0.0">Emulated App 1</app>
    <app id="2" version="1.0.0">Emulated App 2</app>
    <app id="3" version="1.0.0">Emulated App 3</app>
    <app id="4" version="1.0.0">Emulated App 4</app>
    <app id="5" version="1.0.0">Emulated App 5</app>
    <app id="6" version="1.0.0">Emulated App 6</app>
    <app id="7" version="1.0.0">Emulated App 7</app>
    <app id="8" version="1.0.0">Emulated App 8</app>
    <app id="9" version="1.0.0">Emulated App 9</app>
    <app id="10" version="1.0.0">Emulated App 10</app>
</apps>"""

ACTIVE_APP_TEMPLATE = """<active-app>
    <app>Roku</app>
</active-app>"""


class RokuDiscoveryServerProtocol(asyncio.DatagramProtocol):
    """Roku UPNP Discovery protocol."""

    MUTLICAST_TTL = 300
    SSDP_MAX_DELAY = 5
    MULTICAST_GROUP = "239.255.255.250"
    MULTICAST_PORT = 1900
    MULTICAST_SEARCH_MSG = "M-SEARCH * HTTP/1.1"

    MULTICAST_RESPONSE = "HTTP/1.1 200 OK\n" \
                         "Cache-Control: max-age = {ttl}\n" \
                         "ST: roku:ecp\n" \
                         "Location: http://{host_ip}:{port}/\n" \
                         "USN: uuid:roku:ecp:{usn}\n"

    MULTICAST_NOTIFY = "NOTIFY * HTTP/1.1\n" \
                       "HOST: {multicast_ip}:{multicast_port}\n" \
                       "Cache-Control: max-age = {ttl}\n" \
                       "NT: upnp:rootdevice\n" \
                       "NTS: ssdp:alive\n" \
                       "Location: http://{host_ip}:{port}/\n" \
                       "USN: uuid:roku:ecp:{usn}\n"

    transport = None  # type: asyncio.Transport
    host_ip = None
    listen_port = None
    roku_usn = None
    notify_task = None # type: asyncio.Future

    def __init__(self, host_ip, listen_port, advertise_ip, advertise_port,
                 roku_usn, loop=None):
        """Initialize the protocol."""
        if loop:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()
        self.host_ip = host_ip
        self.listen_port = listen_port
        self.roku_usn = roku_usn
        self.upnp_response = self.MULTICAST_RESPONSE.format(
            host_ip=advertise_ip,
            port=advertise_port,
            usn=roku_usn,
            ttl=self.MUTLICAST_TTL)

        self.notify_broadcast = self.MULTICAST_NOTIFY.format(
            host_ip=advertise_ip,
            port=advertise_port,
            multicast_ip=self.MULTICAST_GROUP,
            multicast_port=self.MULTICAST_PORT,
            usn=roku_usn,
            ttl=self.MUTLICAST_TTL)

    def connection_made(self, transport):
        """Set up the multicast socket and schedule the NOTIFY message."""
        self.transport = transport

        sock = self.transport.get_extra_info('socket')  # type: socket.socket
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                        socket.inet_aton(self.MULTICAST_GROUP) +
                        socket.inet_aton(self.host_ip))

        _LOGGER.debug(
            "multicast:started on {}/{}:{}/usn:{}".format(self.MULTICAST_GROUP,
                                                          self.host_ip,
                                                          self.listen_port,
                                                          self.roku_usn))

        self.notify_task = self.loop.create_task(
            self.multicast_notify(self.MUTLICAST_TTL))

    def connection_lost(self, exc):
        """Clean up the protocol."""
        _LOGGER.debug(
            "multicast:closed on {}/{}:{}/usn:{}".format(self.MULTICAST_GROUP,
                                                         self.host_ip,
                                                         self.listen_port,
                                                         self.roku_usn))

        if self.notify_task is not None and not self.notify_task.done():
            self.notify_task.cancel()

    @asyncio.coroutine
    def multicast_notify(self, delay):
        """Broadcast a NOTIFY multicast message."""
        yield from asyncio.sleep(delay)

        if self.transport is None or self.transport.is_closing():
            return

        _LOGGER.debug("multicast:broadcast %s", self.notify_broadcast)
        self.transport.sendto(self.notify_broadcast.encode(),
                              (RokuDiscoveryServerProtocol.MULTICAST_GROUP,
                               RokuDiscoveryServerProtocol.MULTICAST_PORT))

        self.notify_task = self.loop.create_task(
            self.multicast_notify(self.MUTLICAST_TTL))

    @asyncio.coroutine
    def multicast_reply(self, delay, data, addr):
        """Reply to a discovery message."""
        yield from asyncio.sleep(delay)

        if self.transport is None or self.transport.is_closing():
            return

        _LOGGER.debug("multicast:reply %s", self.upnp_response)
        self.transport.sendto(self.upnp_response.encode('utf-8'), addr)

    def datagram_received(self, data, addr):
        """Parse the received datagram and send a reply if needed."""
        data = data.decode('utf-8')

        if data.startswith(self.MULTICAST_SEARCH_MSG) and \
                ("ST: ssdp:all" in data or "ST: roku:ecp" in data):
            _LOGGER.debug("multicast:request %s", data)

            mx_value = data.find("MX:")

            if mx_value != -1:
                mx_delay = int(data[mx_value + 4]) % (self.SSDP_MAX_DELAY + 1)

                delay = random.randrange(0, mx_delay + 1, 1)
            else:
                delay = random.randrange(0, self.SSDP_MAX_DELAY + 1, 1)

            self.loop.create_task(self.multicast_reply(delay, data, addr))


class RokuCommandHandler:
    """Base handler class for Roku commands."""

    KEY_HOME = 'Home'
    KEY_REV = 'Rev'
    KEY_FWD = 'Fwd'
    KEY_PLAY = 'Play'
    KEY_SELECT = 'Select'
    KEY_LEFT = 'Left'
    KEY_RIGHT = 'Right'
    KEY_DOWN = 'Down'
    KEY_UP = 'Up'
    KEY_BACK = 'Back'
    KEY_INSTANTREPLAY = 'InstantReplay'
    KEY_INFO = 'Info'
    KEY_BACKSPACE = 'Backspace'
    KEY_SEARCH = 'Search'
    KEY_ENTER = 'Enter'
    KEY_FINDREMOTE = 'FindRemote'
    KEY_VOLUMEDOWN = 'VolumeDown'
    KEY_VOLUMEMUTE = 'VolumeMute'
    KEY_VOLUMEUP = 'VolumeUp'
    KEY_POWEROFF = 'PowerOff'
    KEY_CHANNELUP = 'ChannelUp'
    KEY_CHANNELDOWN = 'ChannelDown'
    KEY_INPUTTUNER = 'InputTuner'
    KEY_INPUTHDMI1 = 'InputHDMI1'
    KEY_INPUTHDMI2 = 'InputHDMI2'
    KEY_INPUTHDMI3 = 'InputHDMI3'
    KEY_INPUTHDMI4 = 'InputHDMI4'
    KEY_INPUTAV1 = 'InputAV1'

    def on_keydown(self, roku_usn, key):
        """Handle key down command."""
        pass

    def on_keyup(self, roku_usn, key):
        """Handle key up command."""
        pass

    def on_keypress(self, roku_usn, key):
        """Handle key press command."""
        pass

    def launch(self, roku_usn, app_id):
        """Handle launch command."""
        pass


def make_roku_api(loop, handler,
                  host_ip="0.0.0.0", listen_port=8060,
                  advertise_ip=None, advertise_port=None,
                  bind_multicast=True):
    """Intialize the Roku API and discovery protocols."""
    advertise_ip = advertise_ip or host_ip
    advertise_port = advertise_port or listen_port

    roku_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID,
                               "{}:{}".format(advertise_ip, advertise_port)))

    roku_usn = USN_GENERATOR.uuid(
        name="{}{}".format(advertise_ip, advertise_port))

    roku_info = ROKU_INFO_TEMPLATE.format(uuid=roku_uuid, usn=roku_usn)
    device_info = ROKU_DEVICE_INFO_TEMPLATE.format(uuid=roku_uuid,
                                                   usn=roku_usn)

    @asyncio.coroutine
    def roku_root_handler(request):
        return web.Response(body=roku_info,
                            headers={'Content-Type': 'text/xml'})

    @asyncio.coroutine
    def roku_input_handler(request):
        return web.Response()

    @asyncio.coroutine
    def roku_keydown_handler(request):
        key = request.match_info['key']
        handler.on_keydown(roku_usn, key)
        return web.Response()

    @asyncio.coroutine
    def roku_keyup_handler(request):
        key = request.match_info['key']
        handler.on_keyup(roku_usn, key)
        return web.Response()

    @asyncio.coroutine
    def roku_keypress_handler(request):
        key = request.match_info['key']
        handler.on_keypress(roku_usn, key)
        return web.Response()

    @asyncio.coroutine
    def roku_launch_handler(request):
        app_id = request.match_info['id']
        handler.launch(roku_usn, app_id)
        return web.Response()

    @asyncio.coroutine
    def roku_apps_handler(request):
        return web.Response(body=APPS_TEMPLATE,
                            headers={'Content-Type': 'text/xml'})

    @asyncio.coroutine
    def roku_active_app_handler(request):
        return web.Response(body=ACTIVE_APP_TEMPLATE,
                            headers={'Content-Type': 'text/xml'})

    @asyncio.coroutine
    def roku_app_icon_handler(request):
        return web.Response(body='',
                            headers={'Content-Type': 'image/png'})

    @asyncio.coroutine
    def roku_search_handler(request):
        return web.Response()

    @asyncio.coroutine
    def roku_info_handler(request):
        return web.Response(body=device_info,
                            headers={'Content-Type': 'text/xml'})

    discovery_protocol = partial(RokuDiscoveryServerProtocol,
                                 host_ip, listen_port, advertise_ip,
                                 advertise_port, roku_usn)

    # do not bind multicast group on windows even if requested
    if bind_multicast and os.name != "nt":
        multicast_ip = RokuDiscoveryServerProtocol.MULTICAST_GROUP
    else:
        multicast_ip = host_ip

    discovery_endpoint = loop.create_datagram_endpoint(
        discovery_protocol,
        local_addr=(multicast_ip, RokuDiscoveryServerProtocol.MULTICAST_PORT),
        reuse_address=True)

    app = web.Application(loop=loop)

    app.router.add_route('GET', "/", roku_root_handler)

    app.router.add_route('POST', "/keydown/{key}", roku_keydown_handler)
    app.router.add_route('POST', "/keyup/{key}", roku_keyup_handler)
    app.router.add_route('POST', "/keypress/{key}", roku_keypress_handler)
    app.router.add_route('POST', "/launch/{id}", roku_launch_handler)
    app.router.add_route('POST', "/input", roku_input_handler)
    app.router.add_route('POST', "/search", roku_search_handler)

    app.router.add_route('GET', "/query/apps", roku_apps_handler)
    app.router.add_route('GET', "/query/icon/{id}", roku_app_icon_handler)
    app.router.add_route('GET', "/query/active-app", roku_active_app_handler)
    app.router.add_route('GET', "/query/device-info", roku_info_handler)

    api_endpoint = loop.create_server(app.make_handler(), host_ip, listen_port)

    return discovery_endpoint, api_endpoint
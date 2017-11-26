import asyncio
import base64
import logging
import random
import socket
import uuid
from functools import partial

import shortuuid
from aiohttp import web

from .placeholder_image import APP_PLACEHOLDER_IMAGE

USN_GENERATOR = shortuuid.ShortUUID()

_LOGGER = logging.getLogger(__name__)

ROKU_INFO_TEMPLATE = """<root xmlns="urn:schemas-upnp-org:device-1-0">
  <specVersion>
  <major>1</major>
  <minor>0</minor>
  </specVersion>
  <device>
  <deviceType>urn:roku-com:device:player:1-0</deviceType>
  <friendlyName>Emulated Roku {usn}</friendlyName>
  <manufacturer>Roku</manufacturer>
  <manufacturerURL>http://www.roku.com/</manufacturerURL>
  <modelDescription>Roku Streaming Player Network Media</modelDescription>
  <modelName>Roku 4</modelName>
  <modelNumber>4400x</modelNumber>
  <modelURL>http://www.roku.com/</modelURL>
  <serialNumber>4E7552064275</serialNumber>
  <UDN>uuid:{uuid}</UDN>
  <serviceList>
  <service>
  <serviceType>urn:roku-com:service:ecp:1</serviceType>
  <serviceId>urn:roku-com:serviceId:ecp1-0</serviceId>
  <controlURL/>
  <eventSubURL/>
  <SCPDURL>ecp_SCPD.xml</SCPDURL>
  </service>
  <service>
  <serviceType>urn:dial-multiscreen-org:service:dial:1</serviceType>
  <serviceId>urn:dial-multiscreen-org:serviceId:dial1-0</serviceId>
  <controlURL/>
  <eventSubURL/>
  <SCPDURL>dial_SCPD.xml</SCPDURL>
  </service>
  </serviceList>
  </device>
</root>"""

ROKU_DEVICE_INFO_TEMPLATE = """<device-info>
  <udn>{uuid}</udn>
  <serial-number>4E7552064275</serial-number>
  <device-id>1GU48T017973</device-id>
  <vendor-name>Roku</vendor-name>
  <model-number>4400X</model-number>
  <model-name>Roku 4</model-name>
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
 <app id="12" version="3.1.6014">Netflix</app>
 <app id="13" version="4.10.13">Amazon Instant Video</app>
 <app id="2016" version="3.2.7">Crackle</app>
 <app id="2285" version="2.7.6">Hulu Plus</app>
 <app id="13842" version="1.3.2">VUDU</app>
 <app id="28" version="3.1.7">Pandora</app>
</apps>"""

ACTIVE_APP_TEMPLATE = """<active-app>
  <app>Roku</app>
</active-app>"""


class RokuDiscoveryServerProtocol(asyncio.DatagramProtocol):
    MULTICAST_GROUP = '239.255.255.250'
    MULTICAST_SEARCH_MSG = 'M-SEARCH * HTTP/1.1'
    MULTICAST_RESPONSE = 'HTTP/1.1 200 OK\r\nCache-Control: max-age = 300 \r\nST: roku:ecp\r\nLocation: http://{host_ip}:{port}/\r\nUSN: {usn}\r\n'

    ROKU_USN_PART = "uuid:roku:ecp:{usn}"

    transport = None  # type: asyncio.Transport
    host_ip = None
    listen_port = None
    roku_usn = None

    def __init__(self, host_ip, listen_port, advertise_ip, advertise_port, roku_usn, loop=None):
        if loop:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()
        self.host_ip = host_ip
        self.listen_port = listen_port
        self.roku_usn = self.ROKU_USN_PART.format(usn=roku_usn)
        self.upnp_response = self.MULTICAST_RESPONSE.format(host_ip=advertise_ip,
                                                            port=advertise_port,
                                                            usn=self.roku_usn)

    def connection_made(self, transport):
        self.transport = transport

        sock = self.transport.get_extra_info('socket')  # type: socket.socket
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                        socket.inet_aton(self.MULTICAST_GROUP) +
                        socket.inet_aton(sock.getsockname()[0]))

        _LOGGER.info('multicast:started on {}/{}:{}/usn:{}'.format(self.MULTICAST_GROUP,
                                                                   self.host_ip, self.listen_port,
                                                                   self.roku_usn))

    def connection_lost(self, exc):
        _LOGGER.info('multicast:closed on {}/{}:{}/usn:{}'.format(self.MULTICAST_GROUP,
                                                                  self.host_ip, self.listen_port,
                                                                  self.roku_usn))

    @asyncio.coroutine
    def multicast_reply(self, delay, data, addr):
        yield from asyncio.sleep(delay)

        _LOGGER.debug("multicast:reply %s", self.upnp_response)
        self.transport.sendto(self.upnp_response.encode('utf-8'), addr)

    def datagram_received(self, data, addr):
        data = data.decode('utf-8')

        if data[0:19] == self.MULTICAST_SEARCH_MSG and \
                        data.find("ST: ssdp:all") != -1:
            _LOGGER.debug("multicast:request %s", data)

            mx_value = data.find("MX:")
            delay = random.randrange(0, int(data[mx_value + 4]) % 5 + 1, 1)

            self.loop.create_task(self.multicast_reply(delay, data, addr))


class RokuEventHandler:
    KEY_HOME = "Home"
    KEY_REV = "Rev"
    KEY_FWD = "Fwd"
    KEY_PLAY = "Play"
    KEY_SELECT = "Select"
    KEY_LEFT = "Left"
    KEY_RIGHT = "Right"
    KEY_DOWN = "Down"
    KEY_UP = "Up"
    KEY_BACK = "Back"
    KEY_INSTANTREPLAY = "InstantReplay"
    KEY_INFO = "Info"
    KEY_BACKSPACE = "Backspace"
    KEY_SEARCH = "Search"
    KEY_ENTER = "Enter"
    KEY_FINDREMOTE = "FindRemote"
    KEY_VOLUMEDOWN = "VolumeDown"
    KEY_VOLUMEMUTE = "VolumeMute"
    KEY_VOLUMEUP = "VolumeUp"
    KEY_POWEROFF = "PowerOff"
    KEY_CHANNELUP = "ChannelUp"
    KEY_CHANNELDOWN = "ChannelDown"
    KEY_INPUTTUNER = "InputTuner"
    KEY_INPUTHDMI1 = "InputHDMI1"
    KEY_INPUTHDMI2 = "InputHDMI2"
    KEY_INPUTHDMI3 = "InputHDMI3"
    KEY_INPUTHDMI4 = "InputHDMI4"
    KEY_INPUTAV1 = "InputAV1"

    def on_keydown(self, roku_usn, key):
        pass

    def on_keyup(self, roku_usn, key):
        pass

    def on_keypress(self, roku_usn, key):
        pass

    def launch(self, roku_usn, app_id):
        pass


def make_roku_api(loop, handler, host_ip='0.0.0.0', listen_port=8060, advertise_ip=None, advertise_port=None):
    advertise_ip = advertise_ip or host_ip
    advertise_port = advertise_port or listen_port

    roku_uuid = str(uuid.uuid5(uuid.NAMESPACE_OID, '{}:{}'.format(advertise_ip, advertise_port)))

    roku_usn = USN_GENERATOR.uuid(name="{}{}".format(advertise_ip, advertise_port))

    roku_info = ROKU_INFO_TEMPLATE.format(uuid=roku_uuid, usn=roku_usn)
    device_info = ROKU_DEVICE_INFO_TEMPLATE.format(uuid=roku_uuid, usn=roku_usn)

    placeholder_icon = base64.b64decode(APP_PLACEHOLDER_IMAGE)

    @asyncio.coroutine
    def roku_root_handler(request):
        return web.Response(body=roku_info, headers={'Content-Type': 'text/xml'})

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
        return web.Response(body=APPS_TEMPLATE, headers={'Content-Type': 'text/xml'})

    @asyncio.coroutine
    def roku_active_app_handler(request):
        return web.Response(body=ACTIVE_APP_TEMPLATE, headers={'Content-Type': 'text/xml'})

    @asyncio.coroutine
    def roku_app_icon_handler(request):
        return web.Response(body=placeholder_icon, headers={'Content-Type': 'image/png'})

    @asyncio.coroutine
    def roku_search_handler(request):
        return web.Response()

    @asyncio.coroutine
    def roku_info_handler(request):
        return web.Response(body=device_info, headers={'Content-Type': 'text/xml'})

    discovery_protocol = partial(RokuDiscoveryServerProtocol,
                                 host_ip, listen_port, advertise_ip, advertise_port, roku_usn)
    discovery_endpoint = loop.create_datagram_endpoint(discovery_protocol,
                                                       local_addr=(host_ip, 1900),
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

    roku_api_endpoint = loop.create_server(app.make_handler(), host_ip, listen_port)

    return discovery_endpoint, roku_api_endpoint

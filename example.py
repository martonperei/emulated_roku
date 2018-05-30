"""Example script for using the Emulated Roku api."""

if __name__ == "__main__":
    import asyncio
    import logging
    import emulated_roku

    logging.basicConfig(level=logging.DEBUG)

    loop = asyncio.get_event_loop()

    servers = []

    async def init(loop):
        discovery_endpoint, roku_api_endpoint = emulated_roku.make_roku_api(
            loop=loop,
            handler=emulated_roku.RokuCommandHandler(),
            host_ip='192.168.1.101')  # !Change Host IP!

        discovery_transport, _ = await discovery_endpoint
        api_server = await roku_api_endpoint

        servers.append(discovery_transport)
        servers.append(api_server)

    loop.run_until_complete(init(loop))

    loop.run_forever()
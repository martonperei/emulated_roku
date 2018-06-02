"""Example script for using the Emulated Roku api."""

if __name__ == "__main__":
    import asyncio
    import logging
    import emulated_roku

    logging.basicConfig(level=logging.DEBUG)

    loop = asyncio.get_event_loop()

    servers = []


    async def init(loop):
        discovery_server, roku_api = await emulated_roku.make_roku_api(
            loop, emulated_roku.RokuCommandHandler(),
            "test_roku", emulated_roku.get_local_ip(), 8060
        )

        servers.append(discovery_server)
        servers.append(roku_api)


    loop.run_until_complete(init(loop))

    loop.run_forever()

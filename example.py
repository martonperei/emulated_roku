if __name__ == "__main__":
    import emulated_roku
    import asyncio
    import logging

    logging.basicConfig(level=logging.DEBUG)

    loop = asyncio.get_event_loop()

    discovery_endpoint, roku_api_endpoint = emulated_roku.make_roku_api(loop=loop,
                                                                        handler=emulated_roku.RokuEventHandler(),
                                                                        host_ip='192.168.1.101')
    loop.run_until_complete(discovery_endpoint)
    loop.run_until_complete(roku_api_endpoint)

    loop.run_forever()

#!/usr/bin/env python3

"""Example script for using the Emulated Roku api."""

if __name__ == "__main__":
    import asyncio
    import logging
    import emulated_roku

    logging.basicConfig(level=logging.DEBUG)

    async def start_emulated_roku():
        roku_api = emulated_roku.EmulatedRokuServer(
            emulated_roku.EmulatedRokuCommandHandler(),
            "test_roku", emulated_roku.get_local_ip(), 8060,
            custom_apps = None
        )

        await roku_api.start()
        await asyncio.Event().wait()

    asyncio.run(start_emulated_roku())

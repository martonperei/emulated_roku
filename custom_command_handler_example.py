"""
Script to run emulated_roku server and interpret Harmony
controller inputs over wifi.
"""
import sys

class myCustomCommandHandler():
    """Base handler class for Roku commands."""
    def on_keydown(self, roku_usn: str, key: str) -> None:
        """Handle key down command."""
        pass

    def on_keyup(self, roku_usn: str, key: str) -> None:
        """Handle key up command."""
        pass

    def on_keypress(self, roku_usn: str, key: str) -> None:
        """Handle key press command."""
        if key == "Down":
            print("task 1")
        elif key == "Info":
            print("task 2")
        pass

    def launch(self, roku_usn: str, app_id: str) -> None:
        """Handle launch command."""
        pass


if __name__ == "__main__":
    import asyncio
    import logging
    import emulated_roku

    logging.basicConfig(level=logging.DEBUG)

    async def start_emulated_roku(loop):
        roku_api = emulated_roku.EmulatedRokuServer(
            loop,
            myCustomCommandHandler(),
            "test_roku",
            emulated_roku.get_local_ip(),
            8060)

        await roku_api.start()


    loop = asyncio.get_event_loop()

    loop.run_until_complete(start_emulated_roku(loop))

    loop.run_forever()

# emulated_roku

Library to emulate the Roku API for Home Assistant and other automation tools. Discovery is tested with Logitech Harmony and Android remotes.

## Installation

```bash
pip install emulated_roku
```

Requires Python 3.12+.

## Usage

Subclass `EmulatedRokuCommandHandler` to handle key press / down / up events and app launches, then start the server:

```python
import asyncio
import emulated_roku

class MyHandler(emulated_roku.EmulatedRokuCommandHandler):
    def on_keypress(self, roku_usn, key):
        print(f"Key pressed: {key}")

    def launch(self, roku_usn, app_id):
        print(f"Launch app: {app_id}")

async def main():
    server = emulated_roku.EmulatedRokuServer(
        MyHandler(),
        "my-roku",
        emulated_roku.get_local_ip(),
        8060,
    )
    await server.start()
    await asyncio.Event().wait()

asyncio.run(main())
```

See [example.py](example.py) for a minimal runnable example.

## Custom apps

The application list can be customized with a comma- or newline-separated string:

```python
server = emulated_roku.EmulatedRokuServer(
    handler, "my-roku", "192.168.1.10", 8060,
    custom_apps="1:Netflix,2:YouTube,3:Plex",
)
```

This produces:

```xml
<apps>
    <app id="1" version="1.0.0">Netflix</app>
    <app id="2" version="1.0.0">YouTube</app>
    <app id="3" version="1.0.0">Plex</app>
</apps>
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[test]
pytest tests/ -v
```

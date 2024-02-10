# Emulated Roku image, takes Harmony control commands
# and routes to configurable API endpoints
#
# Mount your own command handler to plugin into the 
# API and set off custom commands by mounting your
# own script to /server.py in the container.
#
# Image: notchristiangarcia/emulated_roku

# Inherit from python3's alpine image (it's very small)
from python:3-alpine

# Update pip, install emulated_roku
RUN pip3 install --upgrade pip

# *_NO_EXTENSIONS variables needed to build yarl and
# multidict on alpine linux, required for emulated_roku
RUN YARL_NO_EXTENSIONS=1 MULTIDICT_NO_EXTENSIONS=1 pip3 install emulated-roku

COPY docker_server.py /server.py

CMD ["python3", "-u", "/server.py"]

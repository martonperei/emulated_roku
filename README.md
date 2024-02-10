# emulated_roku  
This library is for emulating the Roku API. Discovery is tested with Logitech Harmony and Android remotes.                                                                                                                                                                                                                                                                                  Only key press / down / up events and app launches (10 dummy apps) are implemented in the RokuCommandHandler callback.
Other functionality such as input, search will not work.
See the [example](example.py) on how to use.


## Docker Integration and Deployment
In this repository also lies a Dockerfile file. The Docker image created by the Dockerfile allows for running a user specified `server.py` file. The image defaults to `docker_server.py` but the image can have a volume mounted to read in another server file instead, for example `custom_server.py`.

#### Image creation
Users are able to build and push the image to Dockerhub with the following commands.
```
docker build -t {username}/emulated_roku .
docker push {username}/emulated_roku
```

#### Image usage
Users are now able to use the local or remote emulated_roku image by doing the following.
```
docker run --net=host -v {your custom_server.py file here}:/server.py {username}/emulated_roku
```
The `--net=host` flag allows for the docker container to use all of the host's networking prowess.  
The `-v` flag allows users to specify their own `server.py` file rather than `example.py`.

#### Docker-Compose
The following is also an example of a `docker-compose.yml` that can be configured once and deployed with `docker-compose up -d`. With the `restart` field set to `unless-stopped`, the container will restart after computer shutdown or reboot unless explicitly stopped, allowing users to have an always on emulated_roku server.
```
---
version: "3"
services:
  emulated_roku
    image: {username}/emulated_roku
    container_name: emulated_roku
    network_mode: host
    volumes:
      - {your_server_file_path}.py:/server.py
    restart: unless-stopped
```

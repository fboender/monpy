import os
import json

CONTAINER_DIR="/var/lib/docker/containers"

def docker_containers():
    if not os.path.isdir(CONTAINER_DIR):
        return []

    for container_id in os.listdir(CONTAINER_DIR):
        with open(os.path.join(CONTAINER_DIR, container_id, "config.v2.json"), "r") as fh:
            container_info = json.load(fh)
            yield container_info

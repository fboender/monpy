import os
import json
import subprocess

CONTAINER_DIR="/var/lib/docker/containers"

def docker_containers():
    for container_id in os.listdir(CONTAINER_DIR):
        res = subprocess.run(
            ["docker", "inspect", container_id],
            capture_output=True,
            text=True,
            check=True
        )
        container_info = json.loads(res.stdout)[0]
        yield container_info

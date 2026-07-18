import os
import json
import subprocess

CONTAINER_DIR="/var/lib/docker/containers"

def container(container_id):
    """
    Return docker container information. See `docker_containers()` for more
    info
    """
    res = subprocess.run(
        ["docker", "inspect", container_id],
        capture_output=True,
        text=True,
        check=True
    )
    container_info = json.loads(res.stdout)[0]
    return container_info


def containers(running=None):
    """
    Docker container information.

    If `running` is True, yield only running containers. If `running` is False,
    return only non-running containers. Otherwise (default) if `running` is
    None, return all containers.

    Yields the same information as `docker inspect <CONTAINER_ID>`. Example
    (heavily reduced for brevity and clarity):

        {
            "Id": "dbc39e6af943f88cbacfad4464be80571adbdba6add97f7feebf155aa230b351",
            "Created": "2026-05-19T05:04:35.323092565Z",
            "Path": "/start.sh",
            "Args": ["/usr/bin/supervisord", "-c", "/supervisord.conf"],
            "State": {
                "Status": "running",
                "Running": true,
                "Paused": false,
                "Restarting": false,
                "OOMKilled": false,
                "Dead": false,
                "Pid": 226721,
                "ExitCode": 0,
                "Error": "",
                "StartedAt": "2026-05-19T05:04:35.422219764Z",
                "FinishedAt": "0001-01-01T00:00:00Z",
                "Health": {
                    "Status": "healthy",
                    "FailingStreak": 0,
                    "Log": []
                }
            },
            "Image": "sha256:e5557d9e6846ee7afba96dd9a903926ba9e4b02f4e37c6476fa94ae23790e512",
            "Name": "/nextcloud-aio-apache",
            "RestartCount": 0,
            "HostConfig": {
                "Binds": [
                    "nextcloud_aio_nextcloud:/var/www/html:ro"
                ],
                "PortBindings": {
                    "11000/tcp": [
                        {
                            "HostIp": "127.0.0.1",
                            "HostPort": "11000"
                        }
                    ]
                },
                "RestartPolicy": {
                    "Name": "unless-stopped",
                    "MaximumRetryCount": 0
                }
            },
            "Mounts": [
                {
                    "Type": "volume",
                    "Name": "nextcloud_aio_nextcloud",
                    "Source": "/var/lib/docker/volumes/nextcloud_aio_nextcloud/_data",
                    "Destination": "/var/www/html",
                    "Driver": "local",
                    "Mode": "ro",
                    "RW": false,
                    "Propagation": ""
                }
            ],
            "Config": {
                "Hostname": "nextcloud-aio-apache",
                "ExposedPorts": {
                    "11000/tcp": {},
                    "80/tcp": {}
                },
                "Env": [
                    "HTTPD_PREFIX=/usr/local/apache2",
                    "HTTPD_VERSION=2.4.67",
                ],
                "Cmd": ["/usr/bin/supervisord", "-c", "/supervisord.conf"],
                "Healthcheck": {
                    "Test": ["CMD-SHELL", "/healthcheck.sh"]
                },
                "Image": "ghcr.io/nextcloud-releases/aio-apache:latest",
                "Volumes": {
                    "/mnt/data": {}
                },
                "WorkingDir": "/usr/local/apache2",
                "Entrypoint": ["/start.sh"],
                "Labels": {
                    "org.opencontainers.image.description": "Apache HTTP server with Caddy for Nextcloud All-in-One",
                },
            },
            "NetworkSettings": {
                "Ports": {
                    "11000/tcp": [
                        {
                            "HostIp": "127.0.0.1",
                            "HostPort": "11000"
                        }
                    ],
                    "80/tcp": null
                },
                "Networks": {
                    "nextcloud-aio": {
                        "Gateway": "172.18.0.1",
                        "IPAddress": "172.18.0.10",
                        "DNSNames": [
                            "nextcloud-aio-apache",
                            "dbc39e6af943"
                        ]
                    }
                }
            }
        }
    """
    for container_id in os.listdir(CONTAINER_DIR):
        container_info = container(container_id)
        if running is None or container_info["State"]["Running"] is running:
            yield container_info



def container_outdated(container_info):
    """
    Check if a docker container's image is outdated.

    Requires `skopeo` CLI to be installed:

        $ sudo apt install skopeo

    Returns True if the container image has an update available, or False if
    not.
    """
    image_name = container_info["Config"]["Image"]
    res = subprocess.run(
        ["skopeo", "inspect", f"docker://{image_name}"],
        capture_output=True,
        text=True,
        check=True
    )
    inspect = json.loads(res.stdout)

    local_image_hash = container_info["Image"]
    remote_image_hash = inspect["Digest"]

    return local_image_hash != remote_image_hash

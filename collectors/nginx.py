from urllib.request import Request, urlopen
import logging


logger = logging.getLogger("monpy." + __name__)


def nginx_status(url):
    """
    Read Nginx stub_status info
    (https://nginx.org/en/docs/http/ngx_http_stub_status_module.html)

    Yields:

        {
            "active_connections": 5,
            "accepts": 40,
            "handled": 40,
            "requests": 174,
            "reading": 0,
            "writing": 4,
            "waiting": 1
        }

    See above mentioned URL for what these mean, as they are not very
    intuitive.
    """
    logger.debug("Making HTTP GET call to %s", url)
    req = Request(url)

    with urlopen(req) as response:
        logger.debug("Response status: %s", response.status)
        body = response.read().decode().splitlines()

        if "Active connections" not in body[0]:
            raise ValueError(f"{url} doesn't look like an Nginx status page")

        active_connections = int(body[0].split(":")[1].strip())
        server = body[2].split()
        accepts = int(server[0])
        handled = int(server[1])
        requests = int(server[2])
        conn_status = body[3].split()
        reading = int(conn_status[1])
        writing = int(conn_status[3])
        waiting = int(conn_status[5])

        return {
            "active_connections": active_connections,
            "accepts": accepts,
            "handled": handled,
            "requests": requests,
            "reading": reading,
            "writing": writing,
            "waiting": waiting,
        }

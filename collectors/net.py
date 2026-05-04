import socket
from urllib.request import Request, urlopen
import base64
import json
import socket
import ssl
import datetime


def tcp_connect(host, port, timeout=3, raise_exception=False):
    """
    Test a TCP connection to a port. If `raise_exception` is set to True, the
    exception (if any) is raised.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except (ConnectionRefusedError, TimeoutError):
        if raise_exception is True:
            raise
        else:
            return False

def http(url,
         method="GET",
         data=None,
         headers=None,
         content_type=None,
         timeout=3,
         username=None,
         password=None):
    """
    Make HTTP(s) requests.
    """
    headers = {
        "User-Agent": "monpy/1.0",
    }

    if username is not None and password is not None:
        auth = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {auth}",

    if content_type is not None:
        headers["Content-Type"] = content_type

    req = Request(
        url,
        method=method,
        data=data,
        headers=headers
    )

    with urlopen(req) as response:
        return {
            "status": response.status,
            "body": response.read().decode(),
            "headers": dict(response.headers),
        }

def ssl_cert(host, port=443):
    """
    Fetch information about SSL certificate
    """
    ctx = ssl.create_default_context()

    with socket.create_connection((host, port)) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            cert = ssock.getpeercert()
            cert_bin = ssock.getpeercert(binary_form=True)

    info = {
        "subject": cert.get("subject"),
        "issuer": cert.get("issuer"),
        "version": cert.get("version"),
        "serialNumber": cert.get("serialNumber"),
        "notBefore": cert.get("notBefore"),
        "notAfter": cert.get("notAfter"),
        "subjectAltName": cert.get("subjectAltName"),
    }

    if info["notAfter"]:
        info["notAfter_dt"] = datetime.datetime.strptime(info["notAfter"], "%b %d %H:%M:%S %Y %Z")
    if info["notBefore"]:
        info["notBefore_dt"] = datetime.datetime.strptime(info["notBefore"], "%b %d %H:%M:%S %Y %Z")

    now = datetime.datetime.now()
    info["expiresDays"] = (info["notAfter_dt"] - now).days

    return info

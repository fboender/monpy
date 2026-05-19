import logging
import socket
from urllib.request import Request, urlopen, HTTPError
import base64
import socket
import ssl
import datetime
import subprocess
import xml.etree.ElementTree as ET

from .processes import process_info
from tools import inode_pid_map

logger = logging.getLogger("monpy." + __name__)

TCP_STATES = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
}

def tcp_connect(host, port, timeout=3, raise_exception=False):
    """
    Test a TCP connection to a port. If `raise_exception` is set to True, the
    exception (if any) is raised.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    logger.debug("Testing TCP connect to %s:%s (timeout=%s)", host, port, timeout)
    try:
        s.connect((host, port))
        logger.debug("Connection to %s:%s successfull", host, port)
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

    Returns:

        {
            "status": 200,                 # HTTP status code
            "reason": "<ERROR REASON>",    # Error reason if error occurred
            "body": "<DECODED_BODY_TEXT>", # Body
            "headers": {},                 # Server response headers
            "response_sec": 0.434          # Response time (seconds)
        }

    """
    result = {
        "status": 0,
        "reason": "",
        "body": "",
        "headers": "",
    }

    headers = {
        "User-Agent": "monpy/1.0",
    }

    if username is not None and password is not None:
        auth = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {auth}",

    if content_type is not None:
        headers["Content-Type"] = content_type

    logger.debug("Making HTTP %s call to %s", method, url)
    start = datetime.datetime.now()
    req = Request(
        url,
        method=method,
        data=data,
        headers=headers
    )

    try:
        with urlopen(req) as response:
            result.update(
                {
                    "status": response.status,
                    "body": response.read().decode(),
                    "headers": dict(response.headers),
                }
            )
    except HTTPError as err:
        result.update(
            {
                "status": err.status,
                "body": err.read().decode(),
                "reason": err.reason,
                "headers": dict(err.headers),
            }
        )

    end = datetime.datetime.now()
    response_sec = (end - start).total_seconds() * 1000
    result["response_sec"] = response_sec

    logger.debug("Response status: %s", result["status"])

    return result

def ssl_cert(host, port=443):
    """
    Fetch information about SSL certificate
    """
    def flatten_name(x):
        return {k: v for tup in x for k, v in tup}

    ctx = ssl.create_default_context()

    logger.debug("Creating SSL connection to %s:%s", host, port)
    with socket.create_connection((host, port)) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            cert = ssock.getpeercert()
            cert_bin = ssock.getpeercert(binary_form=True)

    info = {
        "subject": flatten_name(cert.get("subject", [])),
        "issuer": flatten_name(cert.get("issuer", [])),
        "version": cert.get("version"),
        "serial_number": cert.get("serialNumber"),
        "not_before": cert.get("notBefore"),
        "not_after": cert.get("notAfter"),
        "san": dict(cert.get("subjectAltName", [])),  # {'DNS': 'example.com', ...}
    }

    if info["not_after"]:
        info["not_after_dt"] = datetime.datetime.strptime(info["not_after"], "%b %d %H:%M:%S %Y %Z")
    if info["not_before"]:
        info["not_before_dt"] = datetime.datetime.strptime(info["not_before"], "%b %d %H:%M:%S %Y %Z")

    now = datetime.datetime.now()
    info["expires_days"] = (info["not_after_dt"] - now).days

    logger.debug(
        "Certificate (CN='%s') for host %s:%s expires in %s days",
        info["subject"]["commonName"],
        host,
        port,
        info["expires_days"]
    )
    return info

def _netstat_parse_ip(hex_ip, ipv6=False):
    raw = bytes.fromhex(hex_ip)
    if ipv6:
        return socket.inet_ntop(socket.AF_INET6, raw)
    else:
        return socket.inet_ntoa(raw[::-1])

def _netstat_parse_proc(path, inode_map, ipv6=False):
    conns = []
    with open(path) as f:
        next(f)
        for line in f:
            parts = line.split()

            l_ip, l_port = parts[1].split(":")
            r_ip, r_port = parts[2].split(":")

            inode = int(parts[9])
            pids = inode_map.get(inode, [])
            processes = []
            for pid in pids:
                processes.append(process_info(pid))

            conn_info = {
                "family": "ipv6" if ipv6 else "ipv4",
                "local": (_netstat_parse_ip(l_ip, ipv6), int(l_port, 16)),
                "remote": (_netstat_parse_ip(r_ip, ipv6), int(r_port, 16)),
                "state": TCP_STATES.get(parts[3], parts[3]),
                "tx_queue": int(parts[4].split(":")[0], 16),
                "rx_queue": int(parts[4].split(":")[1], 16),
                "timer_active": int(parts[5].split(":")[0], 16),
                "timeout": int(parts[5].split(":")[1], 16),
                "retransmits": int(parts[6], 16),
                "uid": int(parts[7]),
                "inode": inode,
                "pids": pids,
                "processes": processes
            }


            conns.append(conn_info)
    return conns

def netstat():
    inode_map = inode_pid_map()
    return (
        _netstat_parse_proc("/proc/net/tcp", inode_map, ipv6=False) +
        _netstat_parse_proc("/proc/net/tcp6", inode_map, ipv6=True)
    )

def devices(network):
    """
    Discover hosts on network using nmap

    Yields:

        {
            "status": "up",
            "ip": "192.168.1.6",
            "mac": "68:7F:74:06:1B:CE",
            "hostname": "router",
            "vendor": "Cisco-Linksys"
        }
    """
    cmd = [
        "nmap",
        "-oX", "-",
        "-sn", network
    ]
    logger.debug("Discovering hosts using nmap: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8"
    )
    if proc.returncode != 0:
        logger.error("Error running command '%s': %s", " ".join(cmd), proc.stderr)
        proc.check_returncode()

    root = ET.fromstring(proc.stdout)

    for host in root.findall("host"):
        host_info = {
            "status": None,
            "ip": None,
            "mac": None,
            "hostname": None,
            "vendor": None,
        }

        host_info["status"] = host.find("status").get("state")

        for addr in host.findall("address"):
            if addr.get("addrtype") == "ipv4":
                host_info["ip"] = addr.get("addr")
            elif addr.get("addrtype") == "mac":
                host_info["mac"] = addr.get("addr")
                host_info["vendor"] = addr.get("vendor")

        hostnames = host.find("hostnames").findall("hostname")
        if hostnames:
            host_info["hostname"] = hostnames[0].get("name")

        yield host_info

import sys
import socket


class StdErr:
    def __init__(self):
        pass

    def alert(self, msg, check_name):
        fqdn = socket.getfqdn()
        sys.stderr.write(f"{fqdn}: {check_name}: {msg}\n")

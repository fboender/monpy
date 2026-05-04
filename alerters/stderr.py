import sys
import socket


class StdErr:
    def __init__(self):
        pass

    def alert(self, msg):
        fqdn = socket.getfqdn()
        sys.stderr.write(f"{fqdn}: {msg}\n")

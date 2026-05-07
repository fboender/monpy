import logging
import socket
import http.client
import urllib


class Pushover:
    def __init__(self, user_token, app_token):
        self.user_token = user_token
        self.app_token = app_token
        self.logger = logging.getLogger("monpy."+__name__)

    def alert(self, msg, check_name):
        fqdn = socket.getfqdn()
        html_msg = f"MonPy @ <b>{fqdn}</b> alert for '{check_name}': {msg}"

        conn = http.client.HTTPSConnection("api.pushover.net:443")
        conn.request("POST", "/1/messages.json",
          urllib.parse.urlencode({
            "token": self.app_token,
            "user": self.user_token,
            "html": 1,
            "message": html_msg,
          }), { "Content-type": "application/x-www-form-urlencoded" })
        response = conn.getresponse()
        self.logger.info("Sent alert to Pushover. Response code=%s", response.status)

        if response.status != 200:
            body = response.read().decode()
            self.logger.error("pushover response status != 200: %s", body)

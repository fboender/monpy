from io import StringIO
from contextlib import redirect_stdout
from textwrap import dedent
import json
import socket
import datetime
import logging


S_TEXT = 1
S_EVAL = 2

REPORT_TEMPLATE='''
{%
from datetime import datetime, timedelta
%}
<!DOCTYPE html>
<html>
<head>
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta charset="utf-8">
<title></title>
<meta name="description" content="">
<meta name="author" content="">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
    /* reset css */
    html, body, div, span, applet, object, iframe,
    h1, h2, h3, h4, h5, h6, p, blockquote, pre,
    a, abbr, acronym, address, big, cite, code,
    del, dfn, em, img, ins, kbd, q, s, samp,
    small, strike, strong, sub, sup, tt, var,
    b, u, i, center,
    dl, dt, dd, ol, ul, li,
    fieldset, form, label, legend,
    table, caption, tbody, tfoot, thead, tr, th, td,
    article, aside, canvas, details, embed,
    figure, figcaption, footer, header, hgroup,
    menu, nav, output, ruby, section, summary,
    time, mark, audio, video {
        margin: 0;
        padding: 0;
        border: 0;
        font-size: 100%;
        font: inherit;
        vertical-align: baseline;
    }
    /* HTML5 display-role reset for older browsers */
    article, aside, details, figcaption, figure,
    footer, header, hgroup, menu, nav, section {
        display: block;
    }
    body {
        line-height: 1;
    }
    ol, ul {
        list-style: none;
    }
    blockquote, q {
        quotes: none;
    }
    blockquote:before, blockquote:after,
    q:before, q:after {
        content: '';
        content: none;
    }
    table {
        border-collapse: collapse;
        border-spacing: 0;
    }

    /* Main element */
    body {
        font-family: sans-serif;
        color: #303030;
    }
    #wrapper {
        width: 1200px;
        margin: 0 auto;
    }
    h1 {
        color: #30309F;
        font-size: xx-large;
        font-weight: bold;
        margin: 1em 0 1em 0;
    }
    h2 {
        font-size: x-large;
        font-weight: bold;
        margin: 2em 0 0.5em 0;
    }
    table {
        margin-bottom: 3em;
        border-collapse: separate;
        border-spacing: 2px;
    }
    table.maxwidth {
        width: 100%;
    }
    tr.status_err {
        color: #800000;
    }
    tr.active {
        color: #800000;
    }
    tr.old {
        color: #909090;
    }
    th {
        text-align: left;
        padding: 3px 15px 6px 6px;
        font-weight: bold;
        background-color: #606060;
        color: #FFFFFF;
    }
    td {
        padding: 3px 15px 3px 6px;
    }
    td.check_name {
        font-weight: bold;
        font-family: monospace;
        font-size: 1.2em;
    }
    td.check_name span.check_desc {
        color: #999;
        border: 1px solid #999;
        padding: 2px 5px;
        font-size: small;
    }
    .nowrap {
        white-space:nowrap;
    }
    span.status_okay {
        display: block;
        width: 16px;
        height: 16px;
        background-color: #008000;
    }
    span.status_err {
        display: block;
        width: 16px;
        height: 16px;
        background-color: #900000;
    }
    td.align-right {
        text-align: right;
    }

</style>
<link rel="shortcut icon" href="">
</head>
<body>

<div id="wrapper">

<h1>{{ hostname }}</h1>
<table>
    <tr>
        <th>Last run (start)</th>
        <td>{{ last_run_start }}
    </tr>
    <tr>
        <th>Last run (end)</th>
        <td>{{ last_run_end }}
    </tr>
    <tr>
        <th>Duration</th>
        <td>{{ last_run_end - last_run_start }}</td>
    </tr>
</table>

<h2>Check status</h2>
<table class="maxwidth">
    <tr>
        <th>Check</th>
        <th>Status</th>
        <th>Last run</th>
        <th></th>
        <th>Duration</th>
        <th>Check interval</th>
        <th>Alert interval</th>
    </tr>

{%
for check in checks:
    print(f"""
        <tr class="{check['status_class']}">
            <td class="check_name"><span class="check_desc" title="{check['desc']}" data-toggle="tooltip">?</span> {check['name']}</td>
            <td><span class="{check['status_class']}"></span></td>
            <td>{check['last_run_start']}</td>
            <td>{check['last_run_start_ago']} ago</td>
            <td>{check['last_run_end'] - check['last_run_start']}</td>
            <td class="align-right">{check['check_interval']}</td>
            <td class="align-right">{check['alert_interval']}</td>
        </tr>
    """)
%}
</table>

<h2>Alerts</h2>
<table class="maxwidth">
    <tr>
        <th>Check</th>
        <th>Time</th>
        <th>Message</th>
    </tr>

{%
for alert in alerts:
    print(f"""
        <tr class="{alert['active']}">
            <td class="check_name">{alert['check_name']}</td>
            <td class="nowrap">{datetime.fromtimestamp(alert['time_seen'])}</td>
            <td>{alert['msg']}</td>
        </tr>
    """)
%}
</table>

</div>

</body>
</html>
'''

logger = logging.getLogger(__name__)
def run_code(code, vars):
    buf = StringIO()

    with redirect_stdout(buf):
        exec(dedent(code), vars)

    return buf.getvalue()


def tpl(tpl, vars={}):
    """
    Dead-simple templating language
    """
    out = ""

    state = S_TEXT
    cur_pos = 0
    cur_code = ""
    while cur_pos < len(tpl):
        # Switch states and forward position in template depending on current
        # character
        if tpl[cur_pos] == "{" and tpl[cur_pos + 1] == "{":
            # {{
            state = S_EVAL
            cur_pos += 2
        elif tpl[cur_pos] == "}" and tpl[cur_pos + 1] == "}":
            # }}
            out += run_code(f"print(str({cur_code}), end='')", vars)
            state = S_TEXT
            cur_code = ""
            cur_pos += 2
        elif tpl[cur_pos] == "{" and tpl[cur_pos + 1] == "%":
            # {%
            state = S_EVAL
            cur_pos += 2
        elif tpl[cur_pos] == "%" and tpl[cur_pos + 1] == "}":
            # %}
            out += run_code(cur_code, vars)
            state = S_TEXT
            cur_code = ""
            cur_pos += 2
            if tpl[cur_pos] == "\n":
                # Swallow newlines after code block
                cur_pos += 1

        # Consume characters in template depending on state
        try:
            if state == S_EVAL:
                cur_code += tpl[cur_pos]
            elif state == S_TEXT:
                out += tpl[cur_pos]
        except IndexError:
            pass

        cur_pos += 1
    return out

def human_time(secs):
    """
    Return a human-readable representation of elapsed time.
    """
    if int(secs) == 0:
        return "0s"
    sec = datetime.timedelta(seconds=int(secs))
    d = datetime.datetime(1, 1, 1) + sec
    k = ["%dd", "%dh", "%dm", "%ds"]
    v = [d.day-1, d.hour, d.minute, d.second]
    t = [k[i] % (v[i]) for i in range(len(k)) if v[i] > 0]
    return ' '.join(t[:2])


class HTML:
    def __init__(self, out_path="/var/lib/monpy/report.html"):
        self.out_path = out_path

    def render(self, state):
        now = datetime.datetime.now()
        checks = []
        alerts = []
        for check_name, check_info in state["checks"].items():
            last_run_start = datetime.datetime.fromtimestamp(check_info["last_run_start"])
            last_run_start_ago = human_time((now - last_run_start).total_seconds())
            last_run_end = datetime.datetime.fromtimestamp(check_info["last_run_end"])
            duration = (last_run_end - last_run_start).seconds
            next_run = last_run_start + datetime.timedelta(seconds=check_info["check_interval"])
            check_interval_min = int(check_info["check_interval"] / 60)
            alert_interval_min = int(check_info["alert_interval"] / 60)

            status_class = "status_okay"
            for alert in check_info["alerts"].values():
                alert["check_name"] = check_name
                # If the last time an alert was seen was on or after the last time
                # the check was run the alert is currently active
                if alert["time_seen"] >= check_info["last_run_start"]:
                    status_class = "status_err"
                    alert["active"] = "active"
                else:
                    alert["active"] = "old"
                alerts.append(alert)

            checks.append(
                {
                    "name": check_name,
                    "desc": check_info.get("desc", ""),
                    "last_run_start": last_run_start,
                    "last_run_start_ago": last_run_start_ago,
                    "last_run_end": last_run_end,
                    "duration": duration,
                    "next_run": next_run,
                    "check_interval": human_time(check_info["check_interval"]),
                    "alert_interval": human_time(check_info["alert_interval"]),
                    "status_class": status_class,
                }
            )

        fqdn = socket.getfqdn()
        last_run_start = datetime.datetime.fromtimestamp(state["status"]["last_run_start"])
        last_run_end = datetime.datetime.fromtimestamp(state["status"]["last_run_end"])
        duration = (last_run_end - last_run_start).seconds

        out = tpl(
            REPORT_TEMPLATE,
            vars={
                "hostname": fqdn,
                "last_run_start": last_run_start,
                "last_run_end": last_run_end,
                "checks": checks,
                "alerts": sorted(alerts, key=lambda d: d['time_seen'], reverse=True)
            }
        )

        with open(self.out_path, "w") as fh:
            fh.write(out)

from io import StringIO
from contextlib import redirect_stdout
from textwrap import dedent
import json
import socket
import datetime
import logging

import model


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
{%
    if auto_refresh > 0:
        print(f"""<meta http-equiv="refresh" content="{auto_refresh}">""")
%}
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
    }
    table.data th {
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
<table class="info">
    <tr>
        <th>Last run (start):</th>
        <td>{{ last_run_start.isoformat(sep=" ", timespec="seconds") }}
    </tr>
    <tr>
        <th>Last run (end):</th>
        <td>{{ last_run_end.isoformat(sep=" ", timespec="seconds") }}
    </tr>
    <tr>
        <th>Duration:</th>
        <td>{{ f"{(last_run_end - last_run_start).total_seconds():.3f}s" }}</td>
    </tr>
</table>

<h2>Check status</h2>
<table class="data maxwidth">
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
            <td>{check['last_run_start'].isoformat(sep=" ", timespec="seconds")}</td>
            <td>{check['last_run_start_ago']} ago</td>
            <td>{(check['last_run_end'] - check['last_run_start']).total_seconds():.2f}s</td>
            <td class="align-right">{check['check_interval']}s</td>
            <td class="align-right">{check['alert_interval']}s</td>
        </tr>
    """)
%}
</table>

<h2>Alerts</h2>
<table class="data maxwidth">
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
            <td class="nowrap">{alert['last_seen'].isoformat(sep=" ", timespec="seconds")}</td>
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


def human_time(secs, inc_months=False, max_res=None):
    """
    Return a human-readable representation of elapsed time.
    """
    mapping = [
        ("y", True, 60 * 60 * 24 * 365),
        ("mo", inc_months, 60 * 60 * 24 * 30),
        ("d", True, 60 * 60 * 24),
        ("h", True, 60 * 60),
        ("m", True, 60),
        ("s", True, 1)
    ]

    output = []
    for suffix, include, seconds in mapping:
        if include is False:
            continue

        v, secs = divmod(secs, seconds)
        if v > 0:
            output.append(f"{int(v)}{suffix}")

    return " ".join(output[:max_res]) or "0s"


class HTML:
    def __init__(self, out_path="/var/lib/monpy/report.html", auto_refresh=60):
        self.out_path = out_path
        self.auto_refresh = auto_refresh

    def render(self):
        now = datetime.datetime.now()
        cur = model.conn.cursor()

        run_state = {}
        cur.execute(f"SELECT value FROM monpy WHERE key = 'last_run_start'")
        run_state["last_run_start"] = model.str_to_dt(cur.fetchone()[0])
        cur.execute(f"SELECT value FROM monpy WHERE key = 'last_run_end'")
        run_state["last_run_end"] = model.str_to_dt(cur.fetchone()[0])

        cur.execute(f"SELECT * FROM checks")
        checks = [dict(row) for row in cur]
        alerts = []
        for check in checks:
            check["last_run_start"] = model.str_to_dt(check["last_run_start"])
            check["last_run_end"] = model.str_to_dt(check["last_run_end"])
            check["last_run_start_ago"] = human_time((now - check["last_run_start"]).total_seconds())
            check["duration"] = (check["last_run_end"] - check["last_run_start"]).total_seconds()
            check["next_run"] = check["last_run_start"] + datetime.timedelta(seconds=check["check_interval"])

            check["status_class"] = "status_okay"
            cur.execute("SELECT * FROM alerts WHERE check_name = ?", (check["name"], ))
            for alert in [dict(row) for row in cur]:
                # If the last time an alert was seen was on or after the last time
                # the check was run the alert is currently active
                alert["last_seen"] = model.str_to_dt(alert["last_seen"])
                alert["last_sent"] = model.str_to_dt(alert["last_sent"])
                if alert["last_seen"] >= check["last_run_start"]:
                    check["status_class"] = "status_err"
                    alert["active"] = "active"
                else:
                    alert["active"] = "old"
                alerts.append(alert)

        fqdn = socket.getfqdn()
        out = tpl(
            REPORT_TEMPLATE,
            vars={
                "hostname": fqdn,
                "last_run_start": run_state["last_run_start"],
                "last_run_end": run_state["last_run_end"],
                "auto_refresh": self.auto_refresh,
                "checks": checks,
                "alerts": sorted(alerts, key=lambda d: d['last_seen'], reverse=True)
            }
        )

        with open(self.out_path, "w") as fh:
            fh.write(out)

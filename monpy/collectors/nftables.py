import subprocess
import json

def nftables():
    res = subprocess.run(
        ["nft", "-j", "list", "ruleset"],
        capture_output=True,
        text=True,
        check=True
    )

    return json.loads(res.stdout)

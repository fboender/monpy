import logging
import subprocess
import os
import json


from .git import Repo

logger = logging.getLogger(__name__)

def _simplify_cve(raw_cve):
    """
    Simplify a CVE entry.
    """
    cve = {}

    metadata = raw_cve["cveMetadata"]
    cna = raw_cve["containers"]["cna"]
    affected = cna.get("affected", None)

    cve["id"] = metadata["cveId"]
    cve["url"] = f"https://cvefeed.io/vuln/detail/{metadata['cveId']}"
    cve["state"] = metadata["state"].lower()
    cve["title"] = cna.get("title", "")

    cve["description"] = ""
    if "descriptions" in cna:
        cve["description"] = cna["descriptions"][0]["value"]

    cve["vendor"] = "Unknown"
    cve["product"] = "Unknown"
    if affected is not None:
        cve["vendor"] = affected[0].get("vendor", "Unknown")
        cve["product"] = affected[0].get("product", "Unknown")

    return cve

def new(cvelistv5_repo="/var/lib/monpy/cvelistV5", simplified=True):
    """
    Yields CVE information that's newly added the official CVE list (CVE List
    5) github repository.

    You must already have a local clone of the repository:

        $ cd /var/lib/monpy/
        $ git clone https://github.com/CVEProject/cvelistV5.git

    This collector will automatically fetch changes and fast-forward the git
    repo to the latest commit.

    Newly added files in all commits since the last check will be inspected,
    simplified (if `simplified` is True) and yielded:

        {
            "id": "CVE-2026-41567",
            "url": "https://cvefeed.io/vuln/detail/CVE-2026-41567",
            "state": "published",
            "title": "Docker: `PUT /containers/{id}/archive` executes container binary on the host",
            "description": "Moby is an open source container framework. In versions prior to 29.5.1 [...]",
            "vendor": "moby",
            "product": "moby/v2/daemon"
        }
    """
    repo = Repo(cvelistv5_repo)
    prev_commit_hash = repo.log()[0]["hash"]
    repo.fetch()
    repo.fast_forward()

    for commit in repo.log(from_commit=prev_commit_hash):
        for new_cve_path in commit["added"]:
            path = os.path.join(cvelistv5_repo, new_cve_path)
            with open(path, "r") as fh:
                cve = json.load(fh)
                if simplified is True:
                    yield _simplify_cve(cve)
                else:
                    yield cve

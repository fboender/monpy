import logging
import subprocess
import json

logger = logging.getLogger(__name__)


def pip_audit(site_packages_path, pip_audit_path="pip-audit"):
    """
    Use pip-audit on a site-packages path to scan for installed packages with
    vulnerabilities.

    Yields:

        {
            "name": "urllib3",
            "version": "2.6.3",
            "vulnerability_id": "PYSEC-2026-141",
            "fixed": "2.7.0",
            "description": "Cross-origin redirects forward sensitive headers"
        }
    """
    cmd = [
        pip_audit_path,
        "-f", "json",
        "--path", site_packages_path
    ]
    logger.debug("Running: %s", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8"
    )
    # Exit code 0 == okay, exit code 1 == vulnerabilities where found. But
    # that's okay, so we ignore those.
    if proc.returncode not in [0, 1]:
        logger.error("Error running command '%s': %s", " ".join(cmd), proc.stderr)
        proc.check_returncode()

    for dependency in json.loads(proc.stdout)["dependencies"]:
        for vulnerability in dependency["vulns"]:
            yield {
                "name": dependency["name"],
                "version": dependency["version"],
                "vulnerability_id": vulnerability["id"],
                "fixed": ", ".join(vulnerability["fix_versions"]),
                "description": vulnerability["description"]
            }

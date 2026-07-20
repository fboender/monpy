#!/bin/env texttool

import subprocess
import textwrap

def get_readme_toc():
    with open("README.md") as fh:
        return Markdown(fh.read()).toc()

def get_usage():
    res = subprocess.run(
        ["./checks.py", "--help"],
        capture_output=True,
        check=True,
        encoding="UTF-8",
    )
    return textwrap.indent(res.stdout, "    ")

def get_monpy_class():
    with Text("monpy/monpy.py") as doc:
        return textwrap.indent(
            (
                doc.sel(
                    start="class MonPy:",
                    end='"""',
                    end_after=True
                ).end_forward('"""', after=True).extract()
            ),
            "    "
        )

def get_def_check():
    with Text("monpy/monpy.py") as doc:
        return (
            doc.sel(
                start="    def check(",
                end='"""',
                end_after=True
            ).end_forward('"""', after=True).extract()
        )

readme_toc = get_readme_toc()
usage = get_usage()
def_monpy_class = get_monpy_class()
def_check = get_def_check()

with Text("README.md") as doc:
    # Replace existing Table of Contents with up-to-date one
    doc.sel(
        start="<!-- TOC -->\n",
        start_after=True,
        end="\n<!-- EOTOC -->"
    ).replace(readme_toc)

    # Replace Usage with up-to-date one
    doc.sel(
        start="Full usage:\n\n",
        start_after=True,
        end="\nA cronjob can"
    ).replace(usage)

    # Replace `MonPy` class definition with up-to-date one
    doc.sel(
        start="    class MonPy:",
        end='    """',
        end_after=True
    ).end_forward('    """', after=True).replace(def_monpy_class)

    # Replace `check()` definition with up-to-date one
    doc.sel(
        start="    def check(",
        end='"""',
        end_after=True
    ).end_forward('"""', after=True).replace(def_check)

    doc.save()

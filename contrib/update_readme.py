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
        encoding="UTF-8",
    )
    return textwrap.indent(res.stdout, "    ")

def get_def_check():
    with Text("monpy/monpy.py") as doc:
        return (
            doc.sel(start="    def check(", end_after='"""')
               .sel_end_fwd(end_after='"""')
               .extract()
        )

readme_toc = get_readme_toc()
usage = get_usage()
def_check = get_def_check()

with Text("README.md") as doc:
    # Replace existing Table of Contents with up-to-date one
    doc.sel(
        start_after="<!-- TOC -->\n",
        end="\n<!-- EOTOC -->"
    ).replace(readme_toc)

    # Replace Usage with up-to-date one
    doc.sel(
        start_after="Full usage:\n\n",
        end="\nA cronjob can"
    ).replace(usage)

    # Replace `check()` definition with up-to-date one
    doc.sel(
        start="    def check(",
        end_after='"""'
    ).sel_end_fwd(end_after='"""').replace(def_check)

    doc.save()

#!/bin/env python3

import os
from setuptools import setup, find_packages
from monpy import __METADATA__


setup(
    name=__METADATA__["name"],
    version=__METADATA__["version"],
    author=__METADATA__["author"],
    author_email=__METADATA__["author_email"],
    description=__METADATA__["desc"],
    keywords="pure python monitoring system reliability security metrics reporting alert intrusion detection",
    url=__METADATA__["homepage"],
    classifiers=[
        "License :: OSI Approved :: MIT License"
    ],
    python_requires='>=3.10.12',
    packages=find_packages()
)

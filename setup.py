#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
import setuptools
from sonar import version


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()
setuptools.setup(
    name="sonar-tools",
    version=version.PACKAGE_VERSION,
    scripts=["sonar-tools"],
    author="Olivier Korach",
    author_email="olivier.korach@gmail.com",
    description="A collection of utility scripts for SonarQube",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/okorach/sonar-tools",
    project_urls={
        "Bug Tracker": "https://github.com/okorach/sonar-tools/issues",
        "Documentation": "https://github.com/okorach/sonar-tools/README.md",
        "Source Code": "https://github.com/okorach/sonar-tools",
    },
    packages=setuptools.find_packages(),
    package_data={"sonar": ["LICENSE", "audit/rules.json", "audit/sonar-audit.properties"]},
    install_requires=[
        "pytz",
        "argparse",
        "datetime",
        "python-dateutil",
        "requests",
        "jprops",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Lesser General Public License v3 or later (LGPLv3+)",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "sonar-audit = tools.audit:main",
            "sonar-projects-export = tools.projects_export:main",
            "sonar-projects-import = tools.project_import:main",
            "sonar-measures-export = tools.measures_export:main",
            "sonar-housekeeper = tools.housekeeper:main",
            "sonar-issues-sync = tools.findings_sync:main",
            "sonar-findings-sync = tools.findings_sync:main",
            "sonar-custom-measures = tools.cust_measures:main",
            "sonar-issues-export = tools.findings_export:main",
            "sonar-findings-export = tools.findings_export:main",
            "sonar-loc = tools.loc:main",
            "sonar-config = tools.config:main",
            "support-audit = tools.support:main",
        ]
    },
    python_requires=">=3.6",
)

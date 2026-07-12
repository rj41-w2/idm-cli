from setuptools import setup, find_packages
import os
import re

def get_version():
    init_py_path = os.path.join(os.path.dirname(__file__), "idm_cli", "__init__.py")
    with open(init_py_path, "r", encoding="utf-8") as f:
        version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", f.read(), re.M)
        if version_match:
            return version_match.group(1)
        raise RuntimeError("Unable to find version string.")

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

# Read the contents of your README file
with open(os.path.join(os.path.dirname(__file__), "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="idm-cli",
    version=get_version(),
    author="Rehan",
    description="A lightning-fast, universal command-line download manager",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rj41-w2/idm-cli",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "idm_cli": ["browser_extension/*", "browser_extension/**/*"],
    },
    install_requires=requirements,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Environment :: Console",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "idm=idm_cli.ui.cli:app",
        ],
    },
)

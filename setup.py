from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="idm-cli",
    version="1.0.0",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "idm=idm_cli.cli:app",
        ],
    },
)

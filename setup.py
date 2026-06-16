from setuptools import setup, find_packages
import os

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

# Read the contents of your README file
with open(os.path.join(os.path.dirname(__file__), "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="idm-cli",
    version="0.0.1",
    author="Rehan",
    author_email="rehanjamilwattoo@gmail.com",
    description="A lightning-fast, universal command-line download manager",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/rj41-w2/idm-cli",
    packages=find_packages(),
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
            "idm=idm_cli.cli:app",
        ],
    },
)

import io
import os

from setuptools import find_packages, setup

this_directory = os.path.abspath(os.path.dirname(__file__))

with io.open(os.path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

package = {}
with io.open(
    os.path.join(this_directory, "cli115", "__version__.py"),
    encoding="utf-8",
) as f:
    exec(f.read(), package)

setup(
    name=package["__title__"],
    version=package["__version__"],
    author=package["__author__"],
    author_email=package["__author_email__"],
    url=package["__url__"],
    description=package["__description__"],
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    packages=find_packages(include=["cli115*"]),
    python_requires=">=3.12",
    install_requires=[
        "p115client>=0.0.8",
    ],
    entry_points={
        "console_scripts": [
            "115cli=cli115.cli:main",
        ],
    },
    extras_require={
        "dev": [
            "coverage",
        ],
    },
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
    ],
)

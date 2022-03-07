from io import open
from os import path

from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))

with open(path.join(here, "README.md"), encoding="utf-8") as f:
    readme = f.read()

with open(path.join(here, "requirements/production.txt"), encoding="utf-8") as f:
    requires = [req.strip() for req in f if req]


setup(
    name="flask_pydantic_spec",
    version="0.3.1",
    author="Chris Gearing, Simon Hayward, Rob Young, Donald Fleming, Saurabh Jha",
    author_email="chris.gearing@turntown.digital",
    description=(
        "generate OpenAPI document and validate request & response "
        "with Python annotations."
    ),
    long_description=readme,
    long_description_content_type="text/markdown",
    url="https://github.com/turner-townsend/flask-pydantic-spec",
    packages=find_packages(exclude=["examples*", "tests*"]),
    package_data={},
    classifiers=[
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.6",
    install_requires=requires,
    extras_require={
        "flask": ["flask"],
    },
    zip_safe=False,
    entry_points={
        "console_scripts": [],
    },
)

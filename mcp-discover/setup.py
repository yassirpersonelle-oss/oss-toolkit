from setuptools import setup
import shutil, os

# Python can't import files with hyphens, so we provide a copy
if not os.path.exists("mcp_discover.py"):
    try:
        with open("mcp-discover.py", "r") as src:
            with open("mcp_discover.py", "w") as dst:
                dst.write(src.read())
    except:
        pass

setup(
    name="mcp-discover",
    version="1.0.0",
    py_modules=["mcp_discover"],
    description="Turn any codebase into an MCP server in one command",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="yassir",
    license="MIT",
    url="https://github.com/yassirpersonelle-oss/oss-toolkit",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: MIT License",
        "Topic :: Software Development :: Code Generators",
    ],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "mcp-discover=mcp_discover:main",
        ],
    },
)

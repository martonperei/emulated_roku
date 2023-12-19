"""Emulated Roku library."""

from setuptools import setup

setup(name="emulated_roku",
      version="0.3.0",
      description="Library to emulate a roku server to serve as a proxy"
                  "for remotes such as Harmony",
      url="https://gitlab.com/mindig.marton/emulated_roku",
      download_url="https://gitlab.com"
                   "/mindig.marton/emulated_roku"
                   "/repository/archive.zip?ref=0.3.0",
      author="mindigmarton",
      license="MIT",
      packages=["emulated_roku"],
      install_requires=["aiohttp>3"],
      zip_safe=True)

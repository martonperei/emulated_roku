from setuptools import setup

setup(name='emulated_roku',
      version='0.0.2',
      description='Library to emulate a roku server to serve as a proxy for remotes such as Harmony',
      url='https://gitlab.com/mindig.marton/emulated_roku',
      download_url='https://gitlab.com/mindig.marton/emulated_roku/repository/archive.zip?ref=0.0.2',
      author='mindigmarton',
      license='MIT',
      packages=['emulated_roku'],
      install_requires=['aiohttp==2.3.3', 'shortuuid==0.5.0'],
      zip_safe=True) 

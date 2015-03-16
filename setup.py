#!/usr/bin/env python

from setuptools import setup

install_requires=['requests', 'beautifulsoup4']

try:
    import enum
except ImportError:
    install_requires.append('enum34')

setup(name='davislib',
      version='0.1',
      description='Interface to online UC Davis student resources',
      author='Andy Haden',
      author_email='achaden@ucdavis.edu',
      url='https://github.com/andyh2',
      install_requires=install_requires,
      packages=['davislib'],
      zip_safe=False
     )
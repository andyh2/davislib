#!/usr/bin/env python

from setuptools import setup

setup(name='Davislib',
      version='0.1',
      description='Interface for UC Davis\' online student resources',
      author='Andy Haden',
      author_email='achaden@ucdavis.edu',
      url='https://github.com/andyh2',
      install_requires=['requests', 'beautifulsoup4'],
      packages=['davislib']
     )
from setuptools import setup, find_packages, Extension
from imp import load_source
import os

VER = load_source("version", 'morpheo/version.py')

version_tag = "{}".format(VER.__version__)


def get_requirements(filename):
    '''Parse requirement file and transform it to setuptools requirements'''
    from pip.req import parse_requirements
    if os.path.exists(filename):
        return list(str(ir.req) for ir in parse_requirements(filename, session=False))
    else:
        return []

setup(
    name='morpheo',
    version=version_tag,
    author='3Liz',
    author_email='infos@3liz.org',
    maintainer='David Marteau',
    maintainer_email='david.marteau@3liz.org',
    description=VER.__description__,
    url='',
    packages=find_packages(),
    package_data={'morpheo.core':['*.sql'], },
    entry_points={
        'console_scripts': ['morpheo = morpheo.cli:main']
    },
    install_requires=get_requirements('requirements.txt'),
    classifiers=[
        "Programming Language :: Python :: 2.7",
        "Operating System :: POSIX :: Linux",
        "Topic :: Scientific/Engineering :: GIS",
    ],
)


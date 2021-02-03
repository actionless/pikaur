from distutils.core import setup

# To use a consistent encoding
import codecs
from os import path, environ
from typing import Dict, Any

if environ.get('PYPY_BUILD'):
    import setuptools  # pylint: disable=unused-import


HERE = path.abspath(path.dirname(__file__))

with codecs.open(path.join(HERE, 'README.md'), encoding='utf-8') as f:
    LONG_DESCRIPTION = f.read()

SETUP_ARGS: Dict[str, Any] = dict(
    name='pikaur',  # Required
    version='1.6.16',  # Required
    description='AUR helper with minimal dependencies',  # Required
    long_description=LONG_DESCRIPTION,  # Optional
    url='https://github.com/actionless/pikaur',  # Optional
    author='Yauheni Kirylau',  # Optional
    author_email='actionless.loveless@gmail.com',  # Optional
    classifiers=[
        'Development Status :: 5 - Production/Stable',

        'Environment :: Console',

        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Information Technology',
        'Intended Audience :: Other Audience',
        'Intended Audience :: System Administrators',

        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',

        'Operating System :: POSIX :: Linux',

        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',

        'Topic :: Software Development :: Build Tools',
        'Topic :: System :: Archiving :: Packaging',
        'Topic :: System :: Installation/Setup',
        'Topic :: Utilities',
    ],

    # Note that this is a string of words separated by whitespace, not a list.
    keywords='arch linux aur helper',

    packages=["pikaur", ],  # Required
)

EXTRA_ARGS_SETUPTOOLS = dict(
    long_description_content_type="text/markdown",
    install_requires=["pyalpm"],
    entry_points={
        'console_scripts': [
            'pikaur = pikaur.main:main'
        ]
    }
)

if environ.get('PYPY_BUILD'):
    SETUP_ARGS.update(EXTRA_ARGS_SETUPTOOLS)

setup(**SETUP_ARGS)

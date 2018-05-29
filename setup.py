from distutils.core import setup

# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='pikaur',  # Required
    version='0.11.4',  # Required
    description='AUR helper with minimal dependencies',  # Required
    long_description=long_description,  # Optional
    url='https://github.com/actionless/pikaur',  # Optional
    author='Yauheni Kirylau',  # Optional
    author_email='actionless.loveless@gmail.com',  # Optional
    classifiers=[  # Optional
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 4 - Beta',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',

        # Pick your license as you wish
        'License :: OSI Approved :: GPL3 License',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 3.6',
    ],
    # Note that this is a string of words separated by whitespace, not a list.
    keywords='aur helper',  # Optional

    packages=["pikaur", ],  # Required
)

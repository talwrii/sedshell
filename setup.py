import setuptools
import distutils.core

class PyTest(distutils.core.Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import subprocess
        import sys
        errno = subprocess.call([sys.executable, 'test.py'])
        raise SystemExit(errno)

setuptools.setup(
    name='sedshell',
    version=0.1,
    author='Tal Wrii',
    author_email='talwrii@tatw.name',
    description='Interactive, interactively-extendable tool for doing things based on lines',
    license='GPL',
    keywords='shell, command line, cli',
    url='https://github.com/talwrii/sedshell',
    packages=['sedshell'],
    long_description=open('README.md').read(),
    entry_points={
        'console_scripts': ['sedshell=sedshell.sedshell:main']
    },
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 2.7',
        'License :: OSI Approved :: GNU General Public License (GPL)'
    ],
    cmdclass={'test': PyTest},
)

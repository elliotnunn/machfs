from setuptools import setup

setup(
    name='machfs',
    version='0.4dev',
    author='Elliot Nunn',
    author_email='elliotnunn@me.com',
    description='Library for reading and writing Macintosh HFS volumes',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    license='MIT',
    url='https://github.com/elliotnunn/machfs',
    classifiers=[
        'Programming Language :: Python :: 3 :: Only',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: MIT License',
        'Topic :: System :: Filesystems',
        'Development Status :: 3 - Alpha',
    ],
    packages=['machfs'],
    install_requires=['macresources'],
)

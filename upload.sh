#!/bin/sh

rm -rf dist
python3 setup.py sdist bdist_wheel
twine upload dist/*

"""Setup file for pysynapse"""

from os.path import abspath, dirname, join
from setuptools import setup

if __name__ == "__main__":
    readme_file = join(dirname(abspath(__file__)), "README.md")
    with open(readme_file, "r") as f:
        readme = f.read()

    setup(long_description=readme, long_description_content_type="text/markdown")

from setuptools import setup

# Cause I Only Want To Have To Update One File
requirements_file: str = "requirements.txt"
requirements_list = open(file=requirements_file, mode="r").read().strip().split()

setup(
    name='pr_manager',
    version='0.0.1',
    description='Unofficial PR Manager For Dolthub Bounties',
    url='git@github.com:alexis-evelyn/PR-Managment-Client-For-Dolthub.git',
    author='Alexis Evelyn',
    author_email='alexis.a.evelyn+dolthub.pr.manager@gmail.com',
    license='Unlicense',
    packages=['pr_manager'],
    zip_safe=True,
    install_requires=requirements_list
)
# Copyright 2020 Artificial Intelligence Redefined <dev+cogment@ai-r.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.develop import develop as _develop
from setuptools.command.sdist import sdist as _sdist

from distutils import log
from string import Template
from os import path, makedirs
from datetime import datetime
from urllib.request import urlretrieve
from shutil import unpack_archive, rmtree


DEFAULT_COGMENT_API_VERSION = "latest"


def retrieve_cogment_api(package_dir):
    cogment_api_version = DEFAULT_COGMENT_API_VERSION
    try:
        from yaml import load

        fh = open(path.join(package_dir, ".cogment-api.yml"), "r")
        cogment_api_version = load(fh).get(
            "cogment_api_version", DEFAULT_COGMENT_API_VERSION
        )
    except Exception as e:
        pass

    url = "https://cogment.github.io/cogment-api/{cogment_api_version}/cogment-api-{cogment_api_version}.tar.gz".format(
        cogment_api_version=cogment_api_version
    )
    protos_dir = path.join(package_dir, "cogment/api")
    log.info("downloading the cogment api from '{}' to '{}'".format(url, protos_dir))

    # Download the archive to a temp file, will fail if the version doesn't exist or the network
    # is down thus keeping what was alredy downloaded.
    temp_local_filename, _ = urlretrieve(url)

    rmtree(protos_dir, ignore_errors=True)

    makedirs(protos_dir, exist_ok=True)

    unpack_archive(temp_local_filename, protos_dir, "gztar")

    with open(path.join(protos_dir, "cogment-api-retrieval.log"), "wb") as fh:
        data = "cogment api retrieved from {} at {}".format(url, datetime.now())
        data = data.encode("utf-8")
        fh.write(data)
        fh.close()


def build_protos(package_dir):
    from grpc.tools import command

    log.info(
        "generating python implementation of the proto files in '{}'".format(
            package_dir
        )
    )
    command.build_package_protos(package_dir)


def build_version_dot_py(package_dir, version):
    template_filename = path.join(package_dir, "cogment/version.py.in")
    filename = path.join(package_dir, "cogment/version.py")

    log.info("generating version specification file at '{}'".format(filename))

    with open(template_filename, "r") as fh:
        template = Template(fh.read())

    data = template.substitute({"version": version})

    with open(filename, "wb") as fh:
        data = data.encode("utf-8")
        fh.write(data)
        fh.close()


class sdist(_sdist):
    def run(self):
        # honor the --dry-run flag
        if not self.dry_run:
            package_dir = path.abspath(self.distribution.package_dir[""])
            retrieve_cogment_api(package_dir)
            build_version_dot_py(
                package_dir, self.distribution.get_version(),
            )
        super().run()


class build_py(_build_py):
    def run(self):
        super().run()
        # honor the --dry-run flag
        if not self.dry_run:
            package_dir = path.abspath(self.build_lib)
            build_protos(package_dir)


class develop(_develop):
    def run(self):
        # honor the --dry-run flag
        if not self.dry_run:
            package_dir = path.abspath(self.distribution.package_dir[""])
            retrieve_cogment_api(package_dir)
            build_protos(package_dir)
            build_version_dot_py(
                package_dir, self.distribution.get_version(),
            )
        super().run()


# This function accepts a dict containing the keyword arguments that will be passed to setuptools.setup.
# It can then be modified in place as appropriate for your build process.
def build(setup_kwargs):
    setup_kwargs.update(
        {
            "package_dir": {"": "."},
            "setup_requires": ["grpcio-tools>=1.19"],
            "cmdclass": {
                # Executed when the package is installed as a dependency, i.e. when someone does something like pip install cogment.
                "build_py": build_py,
                # Executed when the package is installed for development, using `poetry install`.
                "develop": develop,
                # The 'sdist' command should be used to generate the source distribution of the package.
                # However poetry doesn't use it... this shouldn't be a problem if `poetry install` is executed
                # before.
                "sdist": sdist,
            },
        }
    )

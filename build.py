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
from os import path


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
    data = data.encode("utf-8")

    with open(filename, "wb") as fh:
        fh.write(data)
        fh.close()


class sdist(_sdist):
    def run(self):
        # honor the --dry-run flag
        if not self.dry_run:
            build_version_dot_py(
                path.abspath(self.distribution.package_dir[""]),
                self.distribution.get_version(),
            )
        super().run()


class build_py(_build_py):
    def run(self):
        super().run()
        # honor the --dry-run flag
        if not self.dry_run:
            build_protos(path.abspath(self.build_lib))


class develop(_develop):
    def run(self):
        # honor the --dry-run flag
        if not self.dry_run:
            build_protos(path.abspath(self.distribution.package_dir[""]))
            build_version_dot_py(
                path.abspath(self.distribution.package_dir[""]),
                self.distribution.get_version(),
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

# Copyright 2021 AI Redefined Inc. <dev+cogment@ai-r.com>
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

from datetime import datetime
from distutils import log
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.develop import develop as _develop
from setuptools.command.sdist import sdist as _sdist
from shutil import unpack_archive, rmtree, copytree
from urllib.request import urlretrieve, urlopen
import json
import os
import pkg_resources
import setuptools

COGMENT_LATEST_VERSION = "latest"


def get_cogment_latest_release_version():
    res = urlopen("https://api.github.com/repos/cogment/cogment/releases/latest")
    parsedBody = json.load(res)
    return parsedBody["tag_name"]


def touch(filename):
    with open(filename, 'w') as fp:
        pass


class RetrieveCogmentApi(setuptools.Command):
    description = "retrieve the cogment api"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        # This is executed at the root of the package
        package_dir = os.getcwd()

        import yaml

        # In a lot of context the logs are not displayed,
        # putting everything in a string to be able to create a file output
        retrieve_cogment_api_logs = ""

        fh = open(os.path.join(package_dir, ".cogment-api.yaml"), "r")
        cogment_api_cfg = yaml.load(fh, Loader=yaml.FullLoader)

        cogment_version = cogment_api_cfg.get(
            "cogment_version", COGMENT_LATEST_VERSION
        )
        cogment_api_path = cogment_api_cfg.get("cogment_api_path")

        protos_dir = os.path.join(package_dir, "cogment/api")

        if cogment_api_path:
            cogment_api_absolute_path = os.path.normpath(
                os.path.join(package_dir, cogment_api_path)
            )
            # honor the --dry-run flag
            if not self.dry_run:
                rmtree(protos_dir, ignore_errors=True)
                copytree(cogment_api_absolute_path, protos_dir)
                touch(os.path.join(protos_dir, ".gitkeep"))

            log.info(f"copy cogment api from [{cogment_api_absolute_path}]")
        else:
            if cogment_version == COGMENT_LATEST_VERSION:
                cogment_version = get_cogment_latest_release_version()

            url = f"https://github.com/cogment/cogment/releases/download/{cogment_version}/cogment-api.tar.gz"

            # Download the archive to a temp file, will fail if the version doesn't exist
            # or if the network is down thus keeping what was alredy downloaded.
            temp_local_filename, _ = urlretrieve(url)

            # honor the --dry-run flag
            if not self.dry_run:
                rmtree(protos_dir, ignore_errors=True)
                os.makedirs(protos_dir, exist_ok=True)
                touch(os.path.join(protos_dir, ".gitkeep"))

                unpack_archive(temp_local_filename, os.path.join(package_dir, "cogment"), "gztar")

            log.info(f"download cogment api [{cogment_version}] from [{url}]")


class BuildCogmentApiProtos(setuptools.Command):
    description = 'build the cogment api protos'
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        # This is executed at the root of the package
        package_dir = os.getcwd()

        from grpc.tools import protoc

        # Code inspired from
        # https://github.com/grpc/grpc/blob/v1.43.0/tools/distrib/python/grpcio_tools/grpc_tools/command.py#L23-L47
        proto_files = []
        inclusion_root = os.path.abspath(package_dir)
        for root, _, files in os.walk(os.path.join(package_dir, "cogment")):
            for filename in files:
                if filename.endswith('.proto'):
                    proto_files.append(os.path.abspath(os.path.join(root, filename)))

        well_known_protos_include = pkg_resources.resource_filename(
            'grpc_tools', '_proto')

        # honor the --dry-run flag
        if not self.dry_run:
            for proto_file in proto_files:
                command = [
                    'grpc_tools.protoc',
                    '--proto_path={}'.format(inclusion_root),
                    '--proto_path={}'.format(well_known_protos_include),
                    '--python_out={}'.format(inclusion_root),
                    '--grpc_python_out={}'.format(inclusion_root),
                    proto_file
                ]
                if protoc.main(command) != 0:
                    raise Exception('error: {} failed'.format(command))
                log.info(f"generated python implementation of [{proto_file}]")


class develop(_develop):
    def run(self):
        self.run_command('retrieve_cogment_api')
        self.run_command('build_cogment_api_protos')
        super().run()


class sdist(_sdist):
    def run(self):
        self.run_command('retrieve_cogment_api')
        self.run_command('build_cogment_api_protos')
        super().run()


class build_py(_build_py):
    def run(self):
        self.run_command('build_cogment_api_protos')
        super().run()


setuptools.setup(
    cmdclass={
        "retrieve_cogment_api": RetrieveCogmentApi,
        "build_cogment_api_protos": BuildCogmentApiProtos,
        # Executed when the package is installed as a dependency,
        # i.e. when someone does something like pip install cogment.
        "build_py": build_py,
        "develop": develop,
        "sdist": sdist,
    },
)

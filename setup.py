# Copyright 2019 Age of Minds inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""cogment_sdk packaging."""

from setuptools import setup

with open("README.md", "r") as fh:
    LONG_DESCRIPTION = fh.read()

version = {}
with open("cogment/version.py") as fp:
    exec(fp.read(), version)

setup(name='cogment',
      version=version['__version__'],
      description='Cogment SDK',
      url='https://gitlab.com/cogment/cogment',
      long_description=LONG_DESCRIPTION,
      long_description_content_type="text/markdown",
      author='Artificial Intelligence Redefined',
      author_email='dev+cogment@ai-r.com',
      license='Apache License 2.0',
      packages=['cogment', 'cogment.api'],
      tests_require=['pytest'],
      install_requires=[
          'grpcio>=1.19',
          'grpcio-reflection>=1.19',
          'grpcio-tools>=1.19',
          'protobuf>=3.7'
      ],)

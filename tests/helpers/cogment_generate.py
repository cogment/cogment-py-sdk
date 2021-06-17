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

import subprocess
import os

COGMENT_CLI_IMAGE = os.environ.get("COGMENT_CLI_IMAGE")
COGMENT_CLI = os.environ.get("COGMENT_CLI")

def cogment_generate(
    app_directory,
    docker_image=COGMENT_CLI_IMAGE,
    binary=COGMENT_CLI
):
    if docker_image:
        assert subprocess.run(["docker", "pull",  docker_image]).returncode == 0
        assert subprocess.run(["docker", "run",
                               "--volume", "/var/run/docker.sock:/var/run/docker.sock",
                               "--volume", f"{app_directory}:/cogment",
                               docker_image,
                               "generate",
                               "--python_dir=."
                               ])
    else:
        assert binary
        assert subprocess.run([binary,
                               "generate",
                               "--python_dir=."
                               ], cwd=app_directory)

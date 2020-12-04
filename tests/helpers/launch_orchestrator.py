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

import subprocess
import platform
import tempfile
import os
import warnings

COGMENT_ORCHESTRATOR_IMAGE = os.environ.get('COGMENT_ORCHESTRATOR_IMAGE')
COGMENT_ORCHESTRATOR = os.environ.get('COGMENT_ORCHESTRATOR')

def launch_orchestrator(
    app_directory,
    port,
    docker_image=COGMENT_ORCHESTRATOR_IMAGE,
    binary=COGMENT_ORCHESTRATOR
):
    if docker_image:
        assert subprocess.run(["docker", "pull",  docker_image]).returncode == 0

    config_file = 'cogment.yaml'
    # For platform where docker is runned in a VM, replacing localhost by the special host that loops back to the vm's host
    # cf. https://docs.docker.com/docker-for-mac/networking/#use-cases-and-workarounds
    if docker_image and (platform.system() == 'Windows' or platform.system() == 'Darwin'):
        with open(os.path.join(app_directory, config_file), 'r') as cogment_yaml_in:
            config_file = 'cogment-dockerinvm.yaml'
            with open(os.path.join(app_directory, config_file), 'w') as cogment_yaml_out:
                for line in cogment_yaml_in:
                    cogment_yaml_out.write(line.replace('localhost', 'host.docker.internal'))

    status_dir = tempfile.mkdtemp()
    status_file = os.path.join(status_dir, 'cogment_orchestrator_status')
    if docker_image:
        # fifo don't worker between the host and the running docker image let's be less clever.
        with open(status_file, 'w'): pass
    else:
        os.mkfifo(status_file)

    process = None
    if docker_image:
        process = subprocess.Popen(["docker", "run",
                                    "--volume", f"{status_dir}:/status",
                                    "--volume", f"{app_directory}:/app",
                                    "-p", f"{port}:{port}",
                                    docker_image,
                                    f"--lifecycle_port={port}",
                                    f"--actor_port={port}",
                                    f"--config={config_file}",
                                    "--status_file=/status/cogment_orchestrator_status"
                                    ])
    else:
        process = subprocess.Popen([binary,
                                    f"--lifecycle_port={port}",
                                    f"--actor_port={port}",
                                    f"--status_file={status_file}",
                                    f"--config={config_file}",
                                    ], cwd=app_directory)

    print('Orchestrator starting')
    status = None
    if docker_image:
        while(True):
            with open(status_file, 'r') as status:
                if status.read(1) == "I":
                    break
    else:
        status = open(status_file, 'r')
        assert(status.read(1) == "I")
    print('Orchestrator initialized')
    if docker_image:
        while(True):
            with open(status_file, 'r') as status:
                if status.read(2) == "IR":
                    break
    else:
        assert(status.read(1) == "R")
    print('Orchestrator ready')

    def terminate_orchestrator():
        print('Orchestrator terminating')
        nonlocal status
        process.terminate()
        try:
            process.wait(5)
            if docker_image:
                while(True):
                    with open(status_file, 'r') as status:
                        if status.read(3) == "IRT":
                            break
            else:
                assert(status.read(1) == "T")
                status.close()
            print('Orchestrator terminated')
        except subprocess.TimeoutExpired:
            process.kill()
            warnings.warn("Orchestrator failed to terminate properly.")
            print('Orchestrator killed')
        # Get rid of the status file
        os.remove(status_file)
        os.rmdir(status_dir)

    return terminate_orchestrator

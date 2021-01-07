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

COGMENT_ORCHESTRATOR_IMAGE = os.environ.get("COGMENT_ORCHESTRATOR_IMAGE")
COGMENT_ORCHESTRATOR = os.environ.get("COGMENT_ORCHESTRATOR")

def launch_orchestrator(
    app_directory,
    orchestrator_port,
    test_port,
    docker_image=COGMENT_ORCHESTRATOR_IMAGE,
    binary=COGMENT_ORCHESTRATOR
):
    if docker_image:
        subprocess.run(["docker", "pull",  docker_image])

    config_file_template = "cogment.yaml"
    config_file = f"cogment_{test_port}.yaml"

    test_host = f"grpc://localhost:{test_port}"
    if docker_image and (platform.system() == "Windows" or platform.system() == "Darwin"):
        # For platform where docker is runned in a VM, replacing localhost by the special host that loops back to the vm"s host
        # cf. https://docs.docker.com/docker-for-mac/networking/#use-cases-and-workarounds
        test_host = f"grpc://host.docker.internal:{test_port}"


    with open(os.path.join(app_directory, config_file_template), "r") as cogment_yaml_in:
        with open(os.path.join(app_directory, config_file), "w") as cogment_yaml_out:
            for line in cogment_yaml_in:
                cogment_yaml_out.write(line.replace("grpc://localhost:9001", test_host))

    status_dir = tempfile.mkdtemp()
    status_file = os.path.join(status_dir, "cogment_orchestrator_status")
    if docker_image:
        # fifo don"t worker between the host and the running docker image let"s be less clever.
        with open(status_file, "w"): pass
    else:
        os.mkfifo(status_file)

    process = None
    if docker_image:
        launch_orchestator_args = [
            "docker", "run",
            "--volume", f"{status_dir}:/status",
            "--volume", f"{app_directory}:/app"
        ]
        if platform.system() == "Windows" or platform.system() == "Darwin":
            # For platforms where docker is runned in a VM, we need to expose the orchestrator port
            launch_orchestator_args.extend(["-p", f"{orchestrator_port}:{orchestrator_port}"])
        else:
            # For platforms where it's runned of the host we can use the host network
            launch_orchestator_args.extend([ "--network", "host"])
        
        launch_orchestator_args.extend([
            docker_image,
            f"--lifecycle_port={orchestrator_port}",
            f"--actor_port={orchestrator_port}",
            f"--config={config_file}",
            "--status_file=/status/cogment_orchestrator_status"                        
        ])
        process = subprocess.Popen(launch_orchestator_args)
    else:
        process = subprocess.Popen([binary,
                                    f"--lifecycle_port={orchestrator_port}",
                                    f"--actor_port={orchestrator_port}",
                                    f"--status_file={status_file}",
                                    f"--config={config_file}",
                                    ], cwd=app_directory)

    print("Orchestrator starting")
    status = None
    if docker_image:
        while(True):
            with open(status_file, "r") as status:
                if status.read(1) == "I":
                    break
    else:
        status = open(status_file, "r")
        assert(status.read(1) == "I")
    print("Orchestrator initialized")
    if docker_image:
        while(True):
            with open(status_file, "r") as status:
                if status.read(2) == "IR":
                    break
    else:
        assert(status.read(1) == "R")
    print("Orchestrator ready")

    def terminate_orchestrator():
        print("Orchestrator terminating")
        nonlocal status
        process.terminate()
        try:
            process.wait(5)
            if docker_image:
                with open(status_file, "r") as status:
                    if status.read(3) != "IRT":
                        warnings.warn("Orchestrator failed to update status file.")
            else:
                if (status.read(1) != "T"):
                    warnings.warn("Orchestrator failed to update status file.")
                status.close()
            print("Orchestrator terminated")
        except subprocess.TimeoutExpired:
            process.kill()
            warnings.warn("Orchestrator failed to terminate properly.")
            print("Orchestrator killed")
        # Get rid of the status file
        os.remove(status_file)
        os.rmdir(status_dir)

    return terminate_orchestrator

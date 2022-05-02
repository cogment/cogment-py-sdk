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
import platform
import tempfile
import os
import logging

logger = logging.getLogger("cogment.unit-tests.launcher")

def launch_orchestrator(
    app_directory,
    orchestrator_port,
    test_port,
    cogment_path,
    private_key = None,
    root_cert = None,
    trust_chain = None
):
    params_file_template = "params.yaml"
    params_file = f"params_{test_port}.yaml"

    test_host = f"grpc://localhost:{test_port}"

    with open(os.path.join(app_directory, params_file_template), "r") as cogment_yaml_in:
        with open(os.path.join(app_directory, params_file), "w") as cogment_yaml_out:
            for line in cogment_yaml_in:
                cogment_yaml_out.write(line.replace("<<token_placeholder>>", test_host))

    status_dir = tempfile.mkdtemp()
    status_file = os.path.join(status_dir, "cogment_orchestrator_status")
    os.mkfifo(status_file)

    logger.info(f"Launching orchestrator using [{cogment_path}]")
    cwd = app_directory
    launch_orchestator_args = [
        cogment_path,
        "services",
        "orchestrator",
        f"--status_file={status_file}",
        f"--lifecycle_port={orchestrator_port}",
        f"--actor_port={orchestrator_port}",
        f"--params={params_file}",
        f"--pre_trial_hooks={test_host}",
    ]

    if private_key is not None:
        launch_orchestator_args.extend([f"--private_key={private_key}"])
    if root_cert is not None:
        launch_orchestator_args.extend([f"--root_cert={root_cert}"])
    if trust_chain is not None:
        launch_orchestator_args.extend([f"--trust_chain={trust_chain}"])

    process = subprocess.Popen(args=launch_orchestator_args, cwd=cwd)
    logger.debug(f"Started orchestrator with: {process.args}")

    logger.info("Orchestrator starting")
    status = open(status_file, "r")
    assert(status.read(1) == "I")
    logger.info("Orchestrator initialized")
    assert(status.read(1) == "R")
    logger.info("Orchestrator ready")

    def terminate_orchestrator():
        logger.info("Orchestrator terminating")
        nonlocal status
        process.terminate()
        try:
            process.wait(5)
            if (status.read(1) != "T"):
                logger.warning("Orchestrator failed to update status file.")
            status.close()
            logger.info("Orchestrator terminated")
        except subprocess.TimeoutExpired:
            process.kill()
            logger.warning("Orchestrator failed to terminate properly (it was forcibly killed).")
        # Get rid of the status file
        os.remove(status_file)
        os.rmdir(status_dir)

    return terminate_orchestrator

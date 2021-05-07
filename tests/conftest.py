# Copyright 2021 Artificial Intelligence Redefined <dev+cogment@ai-r.com>
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

import pytest
import sys
import os

from helpers.cogment_generate import cogment_generate

TEST_COGMENT_APP_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test_cogment_app')

@pytest.fixture(scope="session")
def test_cogment_app_dir():
    cogment_generate(TEST_COGMENT_APP_DIR)
    return TEST_COGMENT_APP_DIR


@pytest.fixture(scope="session")
def cog_settings(test_cogment_app_dir):
    sys.path.append(test_cogment_app_dir)
    import cog_settings
    return cog_settings

@pytest.fixture(scope="session")
def data_pb2(test_cogment_app_dir):
    sys.path.append(test_cogment_app_dir)
    import data_pb2
    return data_pb2

def pytest_addoption(parser):
    parser.addoption(
        "--launch-orchestrator", action="store_true", default=False, help="launch a live orchestrator run slow tests"
    )

def pytest_configure(config):
    config.addinivalue_line("markers", "use_orchestrator: mark test as requiring a live orchestrator to run")

def pytest_collection_modifyitems(config, items):
    if config.getoption("--launch-orchestrator"):
        # --launch-orchestrator given in cli: launch the orchestrator
        return
    skip_requiring_orchestrator = pytest.mark.skip(reason="needs --launch-orchestrator option to run")
    for item in items:
        if "use_orchestrator" in item.keywords:
            item.add_marker(skip_requiring_orchestrator)

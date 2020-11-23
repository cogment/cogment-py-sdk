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

import asyncio
import os

import pytest

from cogment import Context

from test_cogment_app import cog_settings
from test_cogment_app.data_pb2 import TrialConfig, Observation
from helpers.launch_orchestrator import launch_orchestrator

TEST_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test_cogment_app')

@pytest.fixture(scope="function")
def orchestrator_endpoint():
    # Launch the orchestrator
    terminate_orchestrator = launch_orchestrator(TEST_DIR, port=9000)

    # Execute the test
    yield f"localhost:{9000}"

    # Terminate the orchestrator
    terminate_orchestrator()


class TestEnvironment:
    @pytest.mark.use_orchestrator
    @pytest.mark.asyncio
    async def test_trial_lifecyle(self, orchestrator_endpoint):
        assert orchestrator_endpoint=="localhost:9000"

        trial_id = None

        trial_controller_call_count=0
        async def trial_controller(control_session):
            print('-- start `trial_controller`')
            nonlocal trial_id
            nonlocal trial_controller_call_count
            trial_id = control_session.get_trial_id()
            trial_controller_call_count+=1
            # TODO: investigate how to do that in a better way or how to get rid of it
            await asyncio.sleep(5)
            print('-- end `trial_controller`')

        environment_call_count=0
        async def environment(environment_session):
            print('-- start `environment`')
            nonlocal environment_call_count
            assert environment_session.get_trial_id() == trial_id
            environment_call_count+=1
            environment_session.end()
            print('-- end `environment`')

        context = Context(cog_project=cog_settings, user_id='test_trial_lifecyle')

        context.register_environment(impl=environment)

        serve_environment = asyncio.create_task(context.serve_all_registered(port=9001))
        await context.start_trial(TrialConfig(), endpoint=orchestrator_endpoint, impl=trial_controller)
        serve_environment.cancel()
        assert trial_id != None
        assert trial_controller_call_count == 1
        assert environment_call_count == 1





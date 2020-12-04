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
import unittest

import pytest

from cogment import Context

from helpers.launch_orchestrator import launch_orchestrator
from helpers.find_free_port import find_free_port

# Works because the `test_cogment_app` directory is added to sys.path in conftest.py
import cog_settings
from data_pb2 import TrialConfig, Observation, Action

TEST_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'test_cogment_app')

@pytest.fixture(scope="function")
def unittest_case():
    return unittest.TestCase()

@pytest.fixture(scope="function")
def cogment_test_setup():
    orchestrator_port=find_free_port()
    test_port=find_free_port()
    # Launch the orchestrator
    terminate_orchestrator = launch_orchestrator(
        TEST_DIR,
        orchestrator_port=orchestrator_port,
        test_port=test_port
    )

    # Execute the test
    yield {"orchestrator_endpoint": f"localhost:{orchestrator_port}", "test_port": test_port }

    # Terminate the orchestrator
    terminate_orchestrator()


class TestIntegration:
    @pytest.mark.use_orchestrator
    @pytest.mark.asyncio
    async def test_environment_controlled_trial(self, cogment_test_setup, unittest_case):
        trial_id = None
        target_tick_count = 10

        trial_controller_call_count=0
        environment_ended_future=asyncio.get_running_loop().create_future()

        async def trial_controller(control_session):
            nonlocal trial_id
            nonlocal trial_controller_call_count
            trial_id = control_session.get_trial_id()
            trial_controller_call_count+=1
            # TODO: investigate how to do that in a better way or how to get rid of it
            await environment_ended_future


        environment_call_count=0
        environment_tick_count = 0

        async def environment(environment_session):
            nonlocal environment_call_count
            nonlocal environment_tick_count
            assert environment_session.get_trial_id() == trial_id
            environment_call_count+=1

            environment_session.start([("*", Observation(observed_value=12))])

            async for event in environment_session.event_loop():
                unittest_case.assertCountEqual(event.keys(),["actions"])
                environment_tick_count += 1

                if environment_tick_count>=target_tick_count:
                    environment_session.end([("*", Observation(observed_value=12))])
                    # TODO: I find it weird to need this break, shouldn't the event loop just end in this case?
                    break
                else:
                    environment_session.produce_observations([("*", Observation(observed_value=12))])


            environment_ended_future.set_result(True)

        agent_call_count=0
        agent_observation_count=0
        agent_final_data_count=0
        async def agent(actor_session):
            nonlocal agent_call_count
            nonlocal agent_observation_count
            nonlocal agent_final_data_count
            assert actor_session.get_trial_id() == trial_id
            agent_call_count+=1

            actor_session.start()

            async for event in actor_session.event_loop():
                if "observation" in event:
                    assert event["observation"].observed_value == 12
                    actor_session.do_action(Action(action_value=-1))
                    agent_observation_count += 1

                if "final_data" in event:
                    assert len(event["final_data"].observations) == 1
                    assert len(event["final_data"].messages) == 0
                    assert len(event["final_data"].rewards) == 0
                    agent_final_data_count += 1

                    assert event["final_data"].observations[0].observed_value == 12

        context = Context(cog_settings=cog_settings, user_id='test_environment_controlled_trial')

        context.register_environment(impl=environment)
        context.register_actor(impl_name="test", impl=agent)

        serve_environment = asyncio.create_task(context.serve_all_registered(
            port=cogment_test_setup["test_port"],
            prometheus_port=find_free_port()
        ))
#         await asyncio.sleep(1) # wait for the grpc server to be up and running.
        await context.start_trial(
            endpoint=cogment_test_setup["orchestrator_endpoint"],
            impl=trial_controller,
            trial_config=TrialConfig()
        )
        assert await environment_ended_future
        await context._grpc_server.stop(grace=5.)
        await serve_environment

        assert trial_id != None
        assert trial_controller_call_count == 1
        assert environment_call_count == 1
        assert environment_tick_count == target_tick_count
        assert agent_call_count == 2
        assert agent_observation_count / agent_call_count == target_tick_count
        # TODO investigate why the final data are never received by the agent
        #assert agent_final_data_count / agent_call_count == 1





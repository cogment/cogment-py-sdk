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
import urllib.request


@pytest.fixture(scope="function")
def unittest_case():
    return unittest.TestCase()


@pytest.fixture(scope="function")
def cogment_test_setup(test_cogment_app_dir):
    orchestrator_port = find_free_port()
    test_port = find_free_port()
    # Launch the orchestrator
    terminate_orchestrator = launch_orchestrator(
        test_cogment_app_dir,
        orchestrator_port=orchestrator_port,
        test_port=test_port
    )

    # Execute the test
    yield {"orchestrator_endpoint": f"localhost:{orchestrator_port}", "test_port": test_port}

    # Terminate the orchestrator
    terminate_orchestrator()


class TestIntegration:
    @pytest.mark.use_orchestrator
    @pytest.mark.asyncio
    async def test_environment_controlled_trial(self, cogment_test_setup, unittest_case, cog_settings, data_pb2):
        trial_id = None
        target_tick_count = 10

        trial_controller_call_count = 0
        environment_ended_future = asyncio.get_running_loop().create_future()

        async def trial_controller(control_session):
            nonlocal trial_id
            nonlocal trial_controller_call_count
            trial_id = control_session.get_trial_id()
            trial_controller_call_count += 1
            # TODO: investigate how to do that in a better way or how to get rid of it
            await environment_ended_future

        environment_call_count = 0
        environment_tick_count = 0

        async def environment(environment_session):
            nonlocal environment_call_count
            nonlocal environment_tick_count
            assert environment_session.get_trial_id() == trial_id
            environment_call_count += 1

            environment_session.start([("*", data_pb2.Observation(observed_value=12))])

            async for event in environment_session.event_loop():
                unittest_case.assertCountEqual(event.keys(), ["actions"])
                environment_tick_count += 1

                if environment_tick_count >= target_tick_count:
                    environment_session.end([("*", data_pb2.Observation(observed_value=12))])
                    # TODO: I find it weird to need this break, shouldn't the event loop just end in this case?
                    break
                elif "actions" in event and environment_tick_count == 1:
                    actors = environment_session.get_active_actors()
                    for actor in actors:
                        user_data = data_pb2.MyFeedbackUserData(a_bool=False, a_float=3.0)
                        environment_session.add_feedback(21.0, 1.0, [actor.actor_name], user_data=user_data)

                        mess = data_pb2.MyMessageUserData(a_string="A personal string", an_int=21)
                        environment_session.send_message(mess, [actor.actor_name])

                    mess = data_pb2.MyMessageUserData(a_string="An universal string", an_int=42)
                    environment_session.send_message(mess, ["*"])
                    environment_session.produce_observations([("*", data_pb2.Observation(observed_value=12))])
                else:
                    environment_session.produce_observations([("*", data_pb2.Observation(observed_value=12))])
            environment_ended_future.set_result(True)

        agent_call_count = 0
        agent_observation_count = 0
        agent_final_data_count = 0
        agent_message_count = 0
        had_universal_message = False
        had_personal_message = False
        total_reward = 0

        async def agent(actor_session):
            nonlocal agent_call_count
            nonlocal agent_observation_count
            nonlocal agent_final_data_count
            nonlocal agent_message_count
            nonlocal had_universal_message
            nonlocal had_personal_message
            nonlocal total_reward
            assert actor_session.get_trial_id() == trial_id
            agent_call_count += 1

            actor_session.start()

            async for event in actor_session.event_loop():

                if "observation" in event:
                    assert event["observation"].observed_value == 12
                    actor_session.do_action(data_pb2.Action(action_value=-1))
                    agent_observation_count += 1

                elif "message" in event:
                    message = event['message']

                    mess = data_pb2.MyMessageUserData()
                    mess.ParseFromString(message[1].value)
                    agent_message_count += 1
                    if mess.an_int == 42:
                        had_universal_message = True
                    elif mess.an_int == 21:
                        had_personal_message = True

                elif "reward" in event:
                    reward = event['reward']
                    total_reward += reward.value
                    assert reward.value == 21.0
                    assert reward.confidence == 1.0

                elif "final_data" in event:
                    assert len(event["final_data"].observations) == 1
                    assert len(event["final_data"].messages) == 0
                    assert len(event["final_data"].rewards) == 0
                    agent_final_data_count += 1

                    assert event["final_data"].observations[0].observed_value == 12

        context = Context(cog_settings=cog_settings, user_id='test_environment_controlled_trial')

        context.register_environment(impl=environment)
        context.register_actor(impl_name="test", impl=agent)

        prometheus_port = find_free_port()
        serve_environment = asyncio.create_task(context.serve_all_registered(
            port=cogment_test_setup["test_port"],
            prometheus_port=prometheus_port
        ))
#         await asyncio.sleep(1) # wait for the grpc server to be up and running.
        await context.start_trial(
            endpoint=cogment_test_setup["orchestrator_endpoint"],
            impl=trial_controller,
            trial_config=data_pb2.TrialConfig()
        )

        prometheus_connection = urllib.request.urlopen("http://localhost:" + str(prometheus_port))
        promethus_bytes = prometheus_connection.read()
        promethus_data = promethus_bytes.decode("utf8")
        prometheus_connection.close()

        index = promethus_data.find("actor_decide_processing_seconds_count")
        assert index != -1
        index = promethus_data.find("actor_class=\"test\"")
        assert index != -1
        index = promethus_data.find("name=\"actor_1\"")
        assert index != -1
        index = promethus_data.find("name=\"actor_2\"")
        assert index != -1
        index = promethus_data.find("environment_update_processing_seconds_count")
        assert index != -1
        index = promethus_data.find("impl_name=\"default\"")
        assert index != -1
        index = promethus_data.find("Can you find anything ?")
        assert index == -1

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
        assert had_universal_message
        assert had_personal_message
        assert agent_message_count == 4
        assert total_reward == 42.0

    @pytest.mark.use_orchestrator
    @pytest.mark.asyncio
    async def test_controller_controlled_trial(self, cogment_test_setup, unittest_case, cog_settings, data_pb2):
        trial_id = None

        trial_controller_call_count = 0

        async def trial_controller(control_session):
            print('--`trial_controller`-- start')
            nonlocal trial_id
            nonlocal trial_controller_call_count
            trial_id = control_session.get_trial_id()
            trial_controller_call_count += 1
            await asyncio.sleep(3)
            print('--`trial_controller`-- terminate_trial')
            await control_session.terminate_trial()
            print('--`trial_controller`-- end')

        environment_call_count = 0
        environment_tick_count = 0
        environment_ended_future = asyncio.get_running_loop().create_future()

        async def environment(environment_session):
            nonlocal environment_call_count
            nonlocal environment_tick_count
            nonlocal environment_ended_future
            assert environment_session.get_trial_id() == trial_id
            environment_call_count += 1

            environment_session.start([("*", data_pb2.Observation(observed_value=0))])

            async for event in environment_session.event_loop():
                environment_tick_count += 1

                if "actions" in event:
                    environment_session.produce_observations(
                        [("*", data_pb2.Observation(observed_value=environment_tick_count))])
                if "final_actions" in event:
                    environment_session.end([("*", data_pb2.Observation(observed_value=environment_tick_count))])
                    # TODO: I find it weird to need this break, shouldn't the event loop just end in this case?
                    break

            environment_ended_future.set_result(True)

        agent_call_count = 0
        agents_tick_count = {}

        async def agent(actor_session):
            nonlocal agent_call_count
            nonlocal agents_tick_count
            assert actor_session.get_trial_id() == trial_id
            agent_call_count += 1
            assert actor_session.name not in agents_tick_count
            agents_tick_count[actor_session.name] = 0

            actor_session.start()

            async for event in actor_session.event_loop():
                print('')
                agents_tick_count[actor_session.name] += 1
                if "observation" in event:
                    assert event["observation"].observed_value == agents_tick_count[actor_session.name] - 1
                    actor_session.do_action(data_pb2.Action(action_value=agents_tick_count[actor_session.name]))

                if "final_data" in event:
                    assert len(event["final_data"].observations) == 1
                    assert len(event["final_data"].messages) == 0
                    assert len(event["final_data"].rewards) == 0

                    assert event["final_data"].observations[0].observed_value == agents_tick_count[actor_session.name] - 1

        context = Context(cog_settings=cog_settings, user_id='test_controller_controlled_trial')

        context.register_environment(impl=environment)
        context.register_actor(impl_name="test", impl=agent)

        serve_environment = asyncio.create_task(context.serve_all_registered(
            port=cogment_test_setup["test_port"],
            prometheus_port=find_free_port()
        ))
        await context.start_trial(
            endpoint=cogment_test_setup["orchestrator_endpoint"],
            impl=trial_controller,
            trial_config=data_pb2.TrialConfig()
        )
        assert await environment_ended_future
        await context._grpc_server.stop(grace=5.)
        await serve_environment

        assert trial_id != None
        assert trial_controller_call_count == 1
        assert environment_call_count == 1
        assert agent_call_count == 2

        assert environment_tick_count > 0

        unittest_case.assertCountEqual(agents_tick_count.keys(), ["actor_1", "actor_2"])
        assert agents_tick_count["actor_1"] == agents_tick_count["actor_2"]

        assert agents_tick_count["actor_1"] == environment_tick_count

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
import logging
import unittest

import pytest

import cogment

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
        controller_trial_id = None
        target_tick_count = 10

        trial_controller_call_count = 0

        async def trial_controller(control_session):
            nonlocal controller_trial_id
            nonlocal trial_controller_call_count
            controller_trial_id = control_session.get_trial_id()
            trial_controller_call_count += 1

        environment_call_count = 0
        environment_tick_count = 0
        environment_trial_id = None

        async def environment(environment_session):
            nonlocal environment_trial_id
            nonlocal environment_call_count
            nonlocal environment_tick_count
            environment_trial_id = environment_session.get_trial_id()
            environment_call_count += 1

            environment_session.start([("*", data_pb2.Observation(observed_value=12))])

            async for event in environment_session.event_loop():
                if event.type == cogment.EventType.FINAL:
                    continue

                assert len(event.actions) == len(environment_session.get_active_actors())
                environment_tick_count += 1

                if environment_tick_count >= target_tick_count:
                    environment_session.end([("*", data_pb2.Observation(observed_value=12))])
                elif event.actions and environment_tick_count == 1:
                    actors = environment_session.get_active_actors()
                    for actor in actors:
                        user_data = data_pb2.MyFeedbackUserData(a_bool=False, a_float=3.0)
                        environment_session.add_reward(21.0, 1.0, [actor.actor_name], user_data=user_data)

                        mess = data_pb2.MyMessageUserData(a_string="A personal string", an_int=21)
                        environment_session.send_message(mess, [actor.actor_name])

                    mess = data_pb2.MyMessageUserData(a_string="An universal string", an_int=42)
                    environment_session.send_message(mess, ["*"])
                    environment_session.produce_observations([("*", data_pb2.Observation(observed_value=12))])
                else:
                    environment_session.produce_observations([("*", data_pb2.Observation(observed_value=12))])


        agent_call_count = 0
        agent_observation_count = 0
        agent_final_data_count = 0
        agent_message_count = 0
        had_universal_message = False
        had_personal_message = False
        agent_trial_id = {}
        total_reward = 0
        agents_ended = {}
        agents_ended["actor_1"] = asyncio.get_running_loop().create_future()
        agents_ended["actor_2"] = asyncio.get_running_loop().create_future()

        async def agent(actor_session):
            nonlocal agent_call_count
            nonlocal agent_observation_count
            nonlocal agent_final_data_count
            nonlocal agent_message_count
            nonlocal had_universal_message
            nonlocal had_personal_message
            nonlocal total_reward
            nonlocal agents_ended
            nonlocal agent_trial_id
            assert actor_session.name in agents_ended
            agent_trial_id[actor_session.name] = actor_session.get_trial_id()
            agent_call_count += 1

            actor_session.start()

            async for event in actor_session.event_loop():
                if event.observation:
                    assert event.observation.snapshot.observed_value == 12
                    actor_session.do_action(data_pb2.Action(action_value=-1))
                    agent_observation_count += 1

                for message in event.messages:
                    mess = data_pb2.MyMessageUserData()
                    mess.ParseFromString(message.payload.value)
                    agent_message_count += 1
                    if mess.an_int == 42:
                        had_universal_message = True
                    elif mess.an_int == 21:
                        had_personal_message = True

                for reward in event.rewards:
                    total_reward += reward.value
                    assert reward.value == 21.0

                if event.type == cogment.EventType.FINAL:
                    agent_final_data_count += 1

            agents_ended[actor_session.name].set_result(True)

        context = cogment.Context(cog_settings=cog_settings, user_id='test_environment_controlled_trial')

        context.register_environment(impl=environment)
        context.register_actor(impl_name="test", impl=agent)

        prometheus_port = find_free_port()
        served_endp = cogment.ServedEndpoint(cogment_test_setup["test_port"]) 
        serve_environment = asyncio.create_task(context.serve_all_registered(
            served_endpoint=served_endp,
            prometheus_port=prometheus_port
        ))

        endp = cogment.Endpoint(cogment_test_setup["orchestrator_endpoint"])
        await context.start_trial(
            endpoint=endp,
            impl=trial_controller,
            trial_config=data_pb2.TrialConfig()
        )
        assert len(agents_ended) > 0
        await asyncio.wait(agents_ended.values())

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
        index = promethus_data.find("environment_trial_duration_in_second_count")
        assert index != -1
        index = promethus_data.find("impl_name=\"default\"")
        assert index != -1
        index = promethus_data.find("Can you find anything ?")
        assert index == -1

        assert environment_trial_id != None
        assert controller_trial_id != None
        assert "actor_1" in agent_trial_id
        assert "actor_2" in agent_trial_id
        assert controller_trial_id == environment_trial_id
        assert controller_trial_id == agent_trial_id["actor_1"]
        assert controller_trial_id == agent_trial_id["actor_2"]

        assert trial_controller_call_count == 1
        assert environment_call_count == 1
        assert environment_tick_count == target_tick_count
        assert agent_call_count == 2
        assert agent_observation_count / agent_call_count == target_tick_count + 1
        assert agent_final_data_count == 2
        assert had_universal_message
        assert had_personal_message
        assert agent_message_count == 4
        assert total_reward == 42.0

        logging.info(f"test_environment_controlled_trial finished")
        await context._grpc_server.stop(grace=5.)  # To prepare for next test

    @pytest.mark.use_orchestrator
    @pytest.mark.asyncio
    async def test_controller_controlled_trial(self, cogment_test_setup, unittest_case, cog_settings, data_pb2):

        trial_controller_call_count = 0
        async def trial_controller(control_session):
            logging.info('--`trial_controller`-- start')
            nonlocal trial_controller_call_count
            trial_controller_call_count += 1
            await asyncio.sleep(3)
            logging.info('--`trial_controller`-- terminate_trial')
            await control_session.terminate_trial()
            logging.info('--`trial_controller`-- end')


        environment_call_count = 0
        environment_tick_count = 0

        async def environment(environment_session):
            nonlocal environment_call_count
            nonlocal environment_tick_count

            environment_call_count += 1
            environment_tick_count += 1
            environment_session.start([("*", data_pb2.Observation(observed_value=environment_tick_count))])

            async for event in environment_session.event_loop():
                if event.actions:

                    if event.type == cogment.EventType.ACTIVE:
                        action0 = event.actions[0]
                        assert action0.actor_index == 0
                        assert action0.action.action_value == environment_tick_count
                        action1 = event.actions[1]
                        assert action1.actor_index == 1
                        assert action1.action.action_value == environment_tick_count

                    environment_tick_count += 1
                    environment_session.produce_observations(
                        [("*", data_pb2.Observation(observed_value=environment_tick_count))])


        agent_call_count = 0
        agents_tick_count = {}
        agents_ended = {}
        agents_ended["actor_1"] = asyncio.get_running_loop().create_future()
        agents_ended["actor_2"] = asyncio.get_running_loop().create_future()

        async def agent(actor_session):
            nonlocal agent_call_count
            nonlocal agents_tick_count
            nonlocal agents_ended
            agent_call_count += 1
            assert actor_session.name not in agents_tick_count
            assert actor_session.name in agents_ended
            agents_tick_count[actor_session.name] = 0

            actor_session.start()

            async for event in actor_session.event_loop():

                if event.observation:
                    agents_tick_count[actor_session.name] += 1
                    assert event.observation.snapshot.observed_value == agents_tick_count[actor_session.name]
                    actor_session.do_action(data_pb2.Action(action_value=agents_tick_count[actor_session.name]))

                if event.type == cogment.EventType.ENDING:
                    assert event.observation
                    assert len(event.rewards) == 0
                    assert len(event.messages) == 0

                    assert event.observation.snapshot.observed_value == agents_tick_count[actor_session.name]

            agents_ended[actor_session.name].set_result(True)


        context = cogment.Context(cog_settings=cog_settings, user_id='test_controller_controlled_trial')

        context.register_environment(impl=environment)
        context.register_actor(impl_name="test", impl=agent)

        served_endp = cogment.ServedEndpoint(cogment_test_setup["test_port"]) 
        asyncio.create_task(context.serve_all_registered(
            served_endpoint=served_endp,
            prometheus_port=find_free_port()
        ))
        
        endp = cogment.Endpoint(cogment_test_setup["orchestrator_endpoint"])
        await context.start_trial(
            endpoint=endp,
            impl=trial_controller,
            trial_config=data_pb2.TrialConfig()
        )
        await asyncio.wait(agents_ended.values())

        assert trial_controller_call_count == 1
        assert environment_call_count == 1
        assert agent_call_count == 2

        assert environment_tick_count > 0

        unittest_case.assertCountEqual(agents_tick_count.keys(), ["actor_1", "actor_2"])
        assert agents_tick_count["actor_1"] == agents_tick_count["actor_2"]
        assert agents_tick_count["actor_1"] == environment_tick_count

        logging.info(f"test_controller_controlled_trial finished")
        await context._grpc_server.stop(grace=5.)  # To prepare for next test

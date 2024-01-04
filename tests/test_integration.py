# Copyright 2023 AI Redefined Inc. <dev+cogment@ai-r.com>
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
import logging
import urllib.request
from unittest.mock import AsyncMock

import pytest

import cogment

from helpers.find_free_port import find_free_port
from helpers.launch_cogment import launch_orchestrator

logger = logging.getLogger("cogment.unit-tests")


@pytest.fixture(scope="function")
def cogment_test_setup(test_cogment_app_dir, cogment_path):
    orchestrator_port = find_free_port()
    test_port = find_free_port()
    # Launch the orchestrator
    terminate_orchestrator = launch_orchestrator(
        test_cogment_app_dir,
        cogment_path=cogment_path,
        orchestrator_port=orchestrator_port,
        test_port=test_port
    )

    # Execute the test
    yield {
        "orchestrator_endpoint": f"grpc://localhost:{orchestrator_port}",
        "test_port": test_port,
    }

    # Terminate orchestrator
    terminate_orchestrator()


# Base implementations
def create_pre_trial_hook(environment_implementation):
    async def _pre_trial_hook(session):
        session.environment_implementation = environment_implementation
        session.validate()
    return _pre_trial_hook


class TestIntegration:
    @pytest.mark.use_cogment
    @pytest.mark.asyncio
    async def test_environment_controlled_trial(
        self, cogment_test_setup, unittest_case, cog_settings, data_pb2
    ):
        controller_trial_id = None
        target_tick_count = 10
        environment_call_count = 0
        environment_tick_count = 0
        environment_trial_id = None

        async def environment(environment_session):
            nonlocal environment_trial_id
            nonlocal environment_call_count
            nonlocal environment_tick_count

            assert environment_session.config is not None
            assert environment_session.config.env_config_value == 0

            environment_trial_id = environment_session.get_trial_id()
            environment_call_count += 1

            environment_session.start([("*", data_pb2.Observation(observed_value=12))])

            async for event in environment_session.event_loop():
                if event.type == cogment.EventType.FINAL:
                    continue

                assert len(event.actions) == len(
                    environment_session.get_active_actors()
                )
                environment_tick_count += 1

                if environment_tick_count == 1:
                    logger.debug(f"--Sending message and rewards to Actors")

                    actors = environment_session.get_active_actors()
                    for actor in actors:
                        user_data = data_pb2.MyFeedbackUserData(
                            a_bool=False, a_float=3.0
                        )
                        environment_session.add_reward(
                            21.0, 1.0, [actor.actor_name], user_data=user_data
                        )

                        msg = data_pb2.MyMessageUserData(
                            a_string="A personal string", an_int=21
                        )
                        environment_session.send_message(msg, [actor.actor_name])

                    msg = data_pb2.MyMessageUserData(
                        a_string="An universal string", an_int=42
                    )
                    environment_session.send_message(msg, ["*"])

                if environment_tick_count >= target_tick_count:
                    environment_session.end(
                        [("*", data_pb2.Observation(observed_value=12))]
                    )
                else:
                    environment_session.produce_observations(
                        [("*", data_pb2.Observation(observed_value=12))]
                    )

        pre_hook_called_count = 0

        async def pre_trial_hook(session):
            nonlocal pre_hook_called_count

            assert session.trial_config is not None
            assert session.trial_config.trial_config_value == 31
            assert session.trial_config.env_config is not None

            session.environment_config = session.trial_config.env_config

            session.actors.append(
                {
                    "name": "client_1",
                    "actor_class": "my_actor_class_1",
                    "endpoint": "client",
                    "implementation": "",
                    "config": None,
                }
            )

            pre_hook_called_count += 1

            session.validate()

        agent_call_count = 0
        agent_observation_count = 0
        agent_final_data_count = 0
        agent_message_count = 0
        had_universal_message = False
        had_personal_message = False
        had_message_from_client = 0
        had_reward_from_client = 0
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
            nonlocal had_message_from_client
            nonlocal had_reward_from_client
            nonlocal total_reward
            nonlocal agents_ended
            nonlocal agent_trial_id
            assert actor_session.name in agents_ended
            agent_trial_id[actor_session.name] = actor_session.get_trial_id()
            agent_call_count += 1

            actor_session.start()

            last_tick_id = 0
            async for event in actor_session.event_loop():
                if event.observation:
                    assert event.observation.snapshot.observed_value == 12
                    assert last_tick_id == event.observation.tick_id
                    last_tick_id += 1

                    actor_session.do_action(data_pb2.Action(action_value=-1))
                    agent_observation_count += 1

                for message in event.messages:
                    msg = data_pb2.MyMessageUserData()
                    msg.ParseFromString(message.payload.value)
                    if message.sender_name == "client_1":
                        assert actor_session.name == "actor_2"
                        had_message_from_client += 1
                    elif msg.an_int == 42:
                        had_universal_message = True
                        agent_message_count += 1
                    elif msg.an_int == 21:
                        had_personal_message = True
                        agent_message_count += 1

                for reward in event.rewards:
                    for src in reward.all_sources():
                        if src.sender_name == "client_1":
                            had_reward_from_client += 1
                            assert actor_session.name == "actor_1"
                            assert src.value == 30
                            assert src.confidence == 0.5
                        else:
                            total_reward += src.value
                            assert src.value == 21.0

                if event.type == cogment.EventType.FINAL:
                    agent_final_data_count += 1

            agents_ended[actor_session.name].set_result(True)

        client_call_count = 0
        client_observation_count = 0
        client_final_data_count = 0
        client_message_count = 0
        client_had_universal_message = False
        client_had_personal_message = False
        client_total_reward = 0
        agents_ended["client_1"] = asyncio.get_running_loop().create_future()

        async def client_actor(actor_session):
            nonlocal client_call_count
            nonlocal client_observation_count
            nonlocal client_final_data_count
            nonlocal client_message_count
            nonlocal client_had_universal_message
            nonlocal client_had_personal_message
            nonlocal client_total_reward
            nonlocal agents_ended

            assert actor_session.name in agents_ended
            agent_trial_id[actor_session.name] = actor_session.get_trial_id()
            client_call_count += 1

            actor_session.start()

            last_tick_id = 0
            async for event in actor_session.event_loop():
                if event.observation:
                    assert event.observation.snapshot.observed_value == 12
                    assert last_tick_id == event.observation.tick_id
                    last_tick_id += 1

                    actor_session.do_action(data_pb2.Action(action_value=-1))
                    client_observation_count += 1

                    msg = data_pb2.MyMessageUserData(
                        a_string="A message from aclient", an_int=2
                    )
                    actor_session.send_message(msg, ["actor_2"])

                    actor_session.add_reward(30.0, 0.5, ["actor_1"])

                for message in event.messages:
                    msg = data_pb2.MyMessageUserData()
                    msg.ParseFromString(message.payload.value)
                    client_message_count += 1
                    if msg.an_int == 42:
                        client_had_universal_message = True
                    elif msg.an_int == 21:
                        client_had_personal_message = True

                for reward in event.rewards:
                    client_total_reward += reward.value
                    assert reward.value == 21.0

                if event.type == cogment.EventType.FINAL:
                    client_final_data_count += 1

            agents_ended[actor_session.name].set_result(True)

        context = cogment.Context(
            cog_settings=cog_settings, user_id="test_environment_controlled_trial"
        )

        context.register_environment(impl=environment)
        context.register_actor(impl_name="test", impl=agent)
        context.register_actor(
            impl_name="client",
            impl=client_actor,
            actor_classes=[
                "my_actor_class_1",
            ],
        )
        context.register_pre_trial_hook(pre_trial_hook)

        prometheus_port = find_free_port()
        served_endp = cogment.ServedEndpoint(cogment_test_setup["test_port"])
        asyncio.create_task(
            context.serve_all_registered(
                served_endpoint=served_endp, prometheus_port=prometheus_port
            )
        )
        await asyncio.sleep(1)

        endp = cogment.Endpoint(cogment_test_setup["orchestrator_endpoint"])
        controller = context.get_controller(endpoint=endp)

        trial_ended = asyncio.get_running_loop().create_future()

        async def state_tracking(trial_controller):
            nonlocal trial_ended
            logger.debug(f"--Iterating over trial state...")

            state_count = 0
            state_trial_id = []
            state_itor = trial_controller.watch_trials()
            async for info in state_itor:
                logger.debug(f"--Trial state: {info}")
                assert info.trial_id != 0
                assert info.state != cogment.TrialState.UNKNOWN

                if info.state == cogment.TrialState.INITIALIZING:
                    state_trial_id.append(info.trial_id)
                    state_count += 1
                if info.state == cogment.TrialState.PENDING:
                    state_trial_id.append(info.trial_id)
                    state_count += 10
                if info.state == cogment.TrialState.RUNNING:
                    state_trial_id.append(info.trial_id)
                    state_count += 100
                if info.state == cogment.TrialState.TERMINATING:
                    state_trial_id.append(info.trial_id)
                    state_count += 1000
                if info.state == cogment.TrialState.ENDED:
                    state_trial_id.append(info.trial_id)
                    state_count += 10000
                    break

            await state_itor.aclose()
            trial_ended.set_result((state_count, state_trial_id))
            logger.debug(f"--Finished iterating over trial state: trial [{controller_trial_id}] ended")

        asyncio.create_task(state_tracking(controller))
        await asyncio.sleep(1)

        controller_trial_id = await controller.start_trial(
            trial_config=data_pb2.TrialConfig(trial_config_value=31)
        )
        await context.join_trial(
            trial_id=controller_trial_id, endpoint=endp, impl_name="client"
        )

        await trial_ended
        logger.info("--State reported trial ended")

        count, ids = trial_ended.result()
        assert count == 11111
        assert len(ids) == 5
        for id in ids:
            assert id == controller_trial_id

        # Although the trial has ended, the agents could still be processing the last observation
        assert len(agents_ended) == 3
        await asyncio.wait(agents_ended.values())

        prometheus_connection = urllib.request.urlopen(
            "http://localhost:" + str(prometheus_port)
        )
        promethus_bytes = prometheus_connection.read()
        promethus_data = promethus_bytes.decode("utf8")
        prometheus_connection.close()

        index = promethus_data.find("actor_decide_processing_seconds_count")
        assert index != -1
        index = promethus_data.find('impl_name="test"')
        assert index != -1
        index = promethus_data.find('name="actor_1"')
        assert index != -1
        index = promethus_data.find('name="actor_2"')
        assert index != -1
        index = promethus_data.find("environment_trial_duration_in_second_count")
        assert index != -1
        index = promethus_data.find('impl_name="default"')
        assert index != -1
        index = promethus_data.find("Can you find anything ?")
        assert index == -1

        assert environment_trial_id is not None
        assert controller_trial_id is not None
        assert "actor_1" in agent_trial_id
        assert "actor_2" in agent_trial_id
        assert controller_trial_id == environment_trial_id
        assert controller_trial_id == agent_trial_id["actor_1"]
        assert controller_trial_id == agent_trial_id["actor_2"]

        assert environment_call_count == 1
        assert environment_tick_count == target_tick_count
        assert agent_call_count == 2
        assert agent_observation_count / agent_call_count == target_tick_count + 1
        assert agent_final_data_count == 2
        assert had_universal_message
        assert had_personal_message
        assert agent_message_count == 4
        assert total_reward == 42.0
        assert had_message_from_client == 10
        assert had_reward_from_client == 10

        assert client_call_count == 1
        assert client_observation_count == target_tick_count + 1
        assert client_final_data_count == 1
        assert client_had_universal_message
        assert client_had_personal_message
        assert client_message_count == 2
        assert client_total_reward == 21.0

        assert pre_hook_called_count == 1

        logger.info(f"test_environment_controlled_trial finished")
        await context._grpc_server.stop(grace=5.0)  # To prepare for next test

    @pytest.mark.use_cogment
    @pytest.mark.asyncio
    async def test_controller_controlled_trial(
        self, cogment_test_setup, unittest_case, cog_settings, data_pb2
    ):
        environment_call_count = 0
        environment_tick_count = 0

        async def environment(environment_session):
            nonlocal environment_call_count
            nonlocal environment_tick_count

            environment_call_count += 1
            environment_tick_count += 1
            environment_session.start(
                [("*", data_pb2.Observation(observed_value=environment_tick_count))]
            )

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
                        [
                            (
                                "*",
                                data_pb2.Observation(
                                    observed_value=environment_tick_count
                                ),
                            )
                        ]
                    )

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
                    assert (
                        event.observation.snapshot.observed_value ==
                        agents_tick_count[actor_session.name]
                    )
                    actor_session.do_action(
                        data_pb2.Action(
                            action_value=agents_tick_count[actor_session.name]
                        )
                    )

                if event.type == cogment.EventType.ENDING:
                    assert event.observation
                    assert len(event.rewards) == 0
                    assert len(event.messages) == 0

                    assert (
                        event.observation.snapshot.observed_value ==
                        agents_tick_count[actor_session.name]
                    )

            agents_ended[actor_session.name].set_result(True)

        # Explicitely disabling prometheus by not provideing any registry
        context = cogment.Context(
            cog_settings=cog_settings,
            user_id="test_controller_controlled_trial",
            prometheus_registry=None,
        )

        pre_trial_hook = AsyncMock(wraps=create_pre_trial_hook(environment_implementation="test_environment"))
        context.register_pre_trial_hook(pre_trial_hook)
        context.register_environment(impl_name="test_environment", impl=environment)
        context.register_actor(impl_name="test", impl=agent)

        prometheus_port = find_free_port()
        served_endp = cogment.ServedEndpoint(cogment_test_setup["test_port"])
        asyncio.create_task(
            context.serve_all_registered(
                served_endpoint=served_endp, prometheus_port=prometheus_port
            )
        )
        await asyncio.sleep(1)

        with unittest_case.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(f"http://localhost:{prometheus_port}")

        endp = cogment.Endpoint(cogment_test_setup["orchestrator_endpoint"])
        controller = context.get_controller(endpoint=endp)
        logger.info("--starting trial--")
        trial_id = await controller.start_trial(trial_config=data_pb2.TrialConfig())
        logger.info("--trial started--")

        pre_trial_hook.assert_called_once()
        pre_trial_hook.assert_awaited_once()

        await asyncio.sleep(3)

        logger.info("--requesting trial termination--")
        await controller.terminate_trial(trial_id)
        logger.info("--trial termination request sent--")

        await asyncio.wait(agents_ended.values())

        assert environment_call_count == 1
        assert agent_call_count == 2

        assert environment_tick_count > 0

        unittest_case.assertCountEqual(agents_tick_count.keys(), ["actor_1", "actor_2"])
        unittest_case.assertEqual(
            agents_tick_count["actor_1"], agents_tick_count["actor_2"]
        )
        unittest_case.assertGreaterEqual(
            environment_tick_count, agents_tick_count["actor_1"]
        )

        logger.info(f"test_controller_controlled_trial finished")
        await context._grpc_server.stop(grace=5.0)  # To prepare for next test

    @pytest.mark.use_cogment
    @pytest.mark.asyncio
    async def test_actor_order(
        self, cogment_test_setup, unittest_case, cog_settings, data_pb2
    ):
        agents = ["actor_A", "actor_B", "actor_C", "actor_D"]

        async def pre_trial_hook(session):
            host = "grpc://localhost:" + str(cogment_test_setup["test_port"])
            session.actors = [
                {
                    "name": agents[0],
                    "actor_class": "my_actor_class_2",
                    "endpoint": host,
                    "implementation": "basic",
                    "config": None,
                },
                {
                    "name": agents[1],
                    "actor_class": "my_actor_class_1",
                    "endpoint": host,
                    "implementation": "basic",
                    "config": None,
                },
                {
                    "name": agents[2],
                    "actor_class": "my_actor_class_2",
                    "endpoint": host,
                    "implementation": "basic",
                    "config": None,
                },
                {
                    "name": agents[3],
                    "actor_class": "my_actor_class_1",
                    "endpoint": host,
                    "implementation": "basic",
                    "config": None,
                },
            ]

            session.validate()

        async def environment(environment_session):
            actors = environment_session.get_active_actors()
            assert len(actors) == len(agents)
            for i in range(len(agents)):
                assert actors[i].actor_name == agents[i]

            environment_session.start([("*", data_pb2.Observation(observed_value=1))])

            async for event in environment_session.event_loop():
                if event.actions and event.type == cogment.EventType.ACTIVE:
                    for i in range(len(event.actions)):
                        action_i = event.actions[i]
                        assert action_i.actor_index == i  # This may not always be true
                        assert (
                            action_i.action.action_value == action_i.actor_index + 100
                        )

                    if environment_session.get_tick_id() < 3:
                        environment_session.produce_observations(
                            [("*", data_pb2.Observation(observed_value=1))]
                        )
                    elif environment_session.get_tick_id() == 3:
                        environment_session.end(
                            [("*", data_pb2.Observation(observed_value=1))]
                        )

        agents_ended = {}
        for name in agents:
            agents_ended[name] = asyncio.get_running_loop().create_future()

        async def basic_agent(actor_session):
            nonlocal agents_ended
            assert actor_session.name in agents
            assert actor_session.name in agents_ended

            actor_session.start()

            async for event in actor_session.event_loop():
                if event.observation and event.type == cogment.EventType.ACTIVE:
                    agent_index = agents.index(actor_session.name)
                    actor_session.do_action(
                        data_pb2.Action(action_value=agent_index + 100)
                    )

            agents_ended[actor_session.name].set_result(True)

        context = cogment.Context(
            cog_settings=cog_settings,
            user_id="test_actor_order",
            prometheus_registry=None,
        )

        context.register_environment(impl=environment)
        context.register_actor(impl_name="basic", impl=basic_agent)
        context.register_pre_trial_hook(pre_trial_hook)

        served_endp = cogment.ServedEndpoint(cogment_test_setup["test_port"])
        asyncio.create_task(
            context.serve_all_registered(
                served_endpoint=served_endp, prometheus_port=None
            )
        )
        await asyncio.sleep(1)

        endp = cogment.Endpoint(cogment_test_setup["orchestrator_endpoint"])
        controller = context.get_controller(endpoint=endp)
        await controller.start_trial(
            trial_config=data_pb2.TrialConfig(trial_config_value=31)
        )

        await asyncio.wait(agents_ended.values())

        logger.info(f"test_actor_order_trial finished")
        await context._grpc_server.stop(grace=5.0)  # To prepare for next test

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

import grpc
import grpc.experimental.aio

import cogment.api.orchestrator_pb2 as orchestrator
from cogment.actor import _ClientActorSession, Reward
from cogment.api.common_pb2 import TrialActor
from cogment.api.orchestrator_pb2_grpc import ActorEndpointStub
from cogment.delta_encoding import DecodeObservationData
from cogment.trial import Trial

import asyncio


async def read_observations(client_session, action_conn):
    while True:
        reply = await action_conn.read()

        if not reply.final_data:
            for obs_reply in reply.data.observations:
                tick_id = obs_reply.tick_id
                client_session._trial.tick_id = tick_id

                obs = DecodeObservationData(
                    client_session.actor_class,
                    obs_reply.data,
                    client_session._latest_observation
                )
                client_session._new_observation(obs)

            for rew_request in reply.data.rewards():
                reward = Reward()
                reward._set_all(rew_request, -1)
                client_session._new_reward(reward)

            for message in reply.data.messages:
                client_session._new_message(message)

        else:
            client_session._trial.over = True

            package = SimpleNamespace(observations=[], rewards=[], messages=[])
            tick_id = None

            for obs_reply in reply.data.observations():
                tick_id = obs_reply.tick_id
                obs = DecodeObservationData(
                    agent_session.actor_class,
                    obs_reply.data,
                    agent_session._latest_observation)
                package.observations.append(obs)

            for rew_request in reply.data.rewards():
                reward = Reward()
                reward._set_all(rew_request, -1)
                package.rewards.append(reward)

            for msg_request in reply.data.messages():
                package.messages.append(msg_request)

            if tick_id is not None:
                client_session._trial.tick_id = tick_id

            await client_session._end(package)

            break


async def write_actions(client_session, action_conn):
    while True:
        act = await client_session._action_queue.get()
        action_req = orchestrator.TrialActionRequest()
        action_req.action.content = act.SerializeToString()
        await action_conn.write(action_req)


class ClientServicer:
    def __init__(self, cog_project, endpoint):
        self.cog_project = cog_project

        channel = grpc.experimental.aio.insecure_channel(endpoint)
        self._actor_stub = ActorEndpointStub(channel)

    async def run(self, trial_id, impl, impl_name, actor_classes, actor_name):

        # TODO: Handle properly the multiple actor classes.  Including "all" classes
        #       when the list is empty
        if actor_name is None:
            act_class = actor_classes[0]
            req = orchestrator.TrialJoinRequest(trial_id, actor_class=act_class)
        else:
            req = orchestrator.TrialJoinRequest(trial_id, actor_name=actor_name)

        reply = await self._actor_stub.JoinTrial(req)

        trial = Trial(reply.trial_id, reply.actors_in_trial, self.cog_project)

        self_info = None
        for info in reply.actors_in_trial:
            if info.name == reply.actor_name:
                self_info = info
                break
        if self_info is None:
            raise InvalidRequestError(f"Unknown agent name: {reply.actor_name}", request=reply)

        joined_actor_class = self.cog_project.actor_classes[self_info.actor_class]
        assert not actor_classes or joined_actor_class in actor_classes

        client_session = _ClientActorSession(
            impl,
            actor_class,
            trial,
            self_info.name,
            impl_name,
        )

        loop = asyncio.get_running_loop()

        metadata = (("trial-id", trial.id), ("actor-name", self_info.name))
        action_conn = self._actor_stub.ActionStream(metadata)

        reader_task = loop.create_task(read_observations(client_session, action_conn))
        writer_task = loop.create_task(write_actions(client_session, action_conn))

        await impl(client_session)

        reader_task.cancel()
        writer_task.cancel()

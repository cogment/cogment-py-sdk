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
        obs = DecodeObservationData(
            client_session.actor_class,
            reply.observation.data,
            client_session._latest_observation
        )
        client_session._new_observation(obs, reply.final)

        if reply.messages:
            for message in reply.messages:
                client_session._new_message(message)

        if reply.feedbacks:
            reward = Reward()
            reward._set_feedbacks(reply.feedbacks)

            # TODO: Fix this to match formula in Orchestrator
            #       or update API to return a reward
            for fdbk in reply.feedbacks:
                reward.value += fdbk.value * fdbk.confidence
                reward.confidence += fdbk.confidence
            client_session._new_reward(reward)


async def write_actions(client_session, action_conn, actor_stub, actor_id):
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

    async def run(self, trial_id, impl, impl_name, actor_classes, actor_id):

        # TODO: Handle properly the multiple actor classes.  Including "all" classes
        #       when the list is empty
        if actor_id == -1:
            actor_class = actor_classes[0]
            req = orchestrator.TrialJoinRequest(trial_id, actor_id, actor_class)
        else:
            req = orchestrator.TrialJoinRequest(trial_id, actor_id, None)

        reply = await self._actor_stub.JoinTrial(req)

        trial = Trial(reply.trial_id, reply.actors_in_trial, self.cog_project)

        self_info = reply.actors_in_trial[reply.actor_id]
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

        action_conn = self._actor_stub.ActionStream(
            metadata=(("trial-id", trial.id), ("actor-id", str(reply.actor_id)))
        )

        reader_task = loop.create_task(read_observations(client_session, action_conn))
        writer_task = loop.create_task(write_actions(client_session, action_conn, self._actor_stub, reply.actor_id))

        await impl(client_session)

        reader_task.cancel()
        writer_task.cancel()

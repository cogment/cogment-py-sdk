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
from cogment.actor import _ClientActorSession
from cogment.api.common_pb2 import TrialActor
from cogment.api.orchestrator_pb2_grpc import TrialLifecycleStub, ActorEndpointStub
from cogment.delta_encoding import DecodeObservationData
from cogment.trial import Trial
from cogment.session import Session

import asyncio
from abc import ABC
from types import SimpleNamespace


class ControlSession(ABC):
    def __init__(self, trial, stub):
        self._trial = trial
        self._lifecycle_stub = stub

    def get_trial_id(self):
        return self._trial.id

    def get_configured_actors(self):
        return [SimpleNamespace(actor_name=actor.name, actor_class=actor.actor_class)
                for actor in self._trial.actors]

    async def terminate_trial(self):
        req = orchestrator.TerminateTrialRequest()
        await self._lifecycle_stub.TerminateTrial(req, metadata=(("trial-id", self._trial.id)))


class _ServedControlSession(ControlSession):
    def __init__(self, trial, stub):
        super().__init__(trial, stub)



async def read_observations(client_session, action_conn):
    while True:
        request = await action_conn.read()
        obs = DecodeObservationData(
            client_session.actor_class,
            request.observation.data,
            client_session._latest_observation
        )
        client_session._new_observation(obs, request.final)

        if request.messages:
            for message in request.messages:
                client_session._new_message(message)

        if request.feedbacks:
            client_session._new_reward(request.feedbacks)


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

    async def run(self, trial_id, impl, impl_name, actor_class, actor_id):
        req = orchestrator.TrialJoinRequest(trial_id, actor_id, actor_class)
        reply = await self._actor_stub.JoinTrial(req)

        trial = Trial(reply.trial_id, reply.actors_in_trial, self.cog_project)

        self_info = reply.actors_in_trial[reply.actor_id]
        joined_actor_class = self.cog_project.actor_classes[self_info.actor_class]
        assert joined_actor_class == actor_class

        client_session = _ClientActorSession(
            impl,
            actor_class,
            trial,
            self_info.name,
            impl_name,
        )

        loop = asyncio.get_running_loop()

        action_conn = self.__actor_stub.ActionStream(
            metadata=(("trial-id", trial.id), ("actor-id", str(reply.actor_id)))
        )

        reader_task = loop.create_task(read_observations(client_session, action_conn))
        writer_task = loop.create_task(write_actions(client_session, action_conn, self.__actor_stub, reply.actor_id))

        await impl(client_session)

        reader_task.cancel()
        writer_task.cancel()

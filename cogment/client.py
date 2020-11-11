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
from cogment.trial import Trial, TrialLifecycle

import asyncio


async def read_observations(client_session, action_conn):
    while True:
        request = await action_conn.read()
        obs = DecodeObservationData(
            client_session.actor_class,
            request.observation.data,
            client_session.latest_observation,
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


class Connection:
    def __init__(self, cog_project, endpoint):
        self.cog_project = cog_project

        channel = grpc.experimental.aio.insecure_channel(endpoint)

        self.__lifecycle_stub = TrialLifecycleStub(channel)
        self.__actor_stub = ActorEndpointStub(channel)

    async def start_trial(self, trial_config, user_id):
        req = orchestrator.TrialStartRequest()
        req.config.content = trial_config.SerializeToString()
        req.user_id = user_id

        rep = await self.__lifecycle_stub.StartTrial(req)
        # added trial_config to following and in trial.py TrialLifecycle
        return TrialLifecycle(rep.trial_id, trial_config, rep.actors_in_trial, self)

    async def terminate(self, trial_id):
        req = orchestrator.TerminateTrialRequest()

        await self.__lifecycle_stub.TerminateTrial(
            req, metadata=(("trial-id", trial_id),)
        )

    async def join_trial(self, trial_id=None, actor_id=-1, actor_class=None, impl=None):

        req = req = orchestrator.TTrialJoinRequest(
            trial_id=trial_id, actor_id=actor_id, actor_class=actor_class
        )

        reply = await self.__actor_stub.JoinTrial(req)

        trial = Trial(
            id_=reply.trial_id, cog_project=self.cog_project, trial_config=None
        )

        trial._add_actors(reply.actors_in_trial)
        trial._add_environment()

        self_info = reply.actors_in_trial[reply.actor_id]
        actor_class = self.cog_project.actor_classes[self_info.actor_class]

        client_session = _ClientActorSession(
            # should it be reply.impl_name, if yes add to .proto
            impl,
            actor_class,
            trial,
            self_info.name,
            "impl_name",
        )

        loop = asyncio.get_running_loop()

        action_conn = self.__actor_stub.ActionStream(
            metadata=(("trial-id", reply.trial_id), ("actor-id", str(reply.actor_id)))
        )

        reader_task = loop.create_task(read_observations(client_session, action_conn))
        writer_task = loop.create_task(
            write_actions(
                client_session, action_conn, self.__actor_stub, reply.actor_id
            )
        )

        await impl(client_session, trial)

        reader_task.cancel()
        writer_task.cancel()

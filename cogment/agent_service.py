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

from cogment.api.agent_pb2_grpc import AgentEndpointServicer

from cogment.api.agent_pb2 import (
    AgentStartReply,
    AgentRewardReply,
    AgentEndReply,
    AgentActionReply,
)

from cogment.utils import list_versions
from cogment.trial import Trial

from cogment.errors import InvalidRequestError
from cogment.delta_encoding import DecodeObservationData
from cogment.actor import _ServedActorSession

import traceback
import atexit
import logging
import typing
import asyncio


def _trial_key(trial_id, actor_id):
    return f"{trial_id}_{actor_id}"


def _impl_can_serve_actor_class(impl, actor_class):
    if isinstance(impl.actor_class, typing.List):
        return any(__impl_can_serve_actor_class(e) for e in impl.actor_class)

    return impl.actor_class == "*" or impl.actor_class == actor_class.id_


async def read_observations(request_iterator, agent_session):
    async for request in request_iterator:
        obs = DecodeObservationData(
            agent_session.actor_class,
            request.observation.data,
            agent_session.latest_observation,
        )
        agent_session._new_observation(obs, request.final)


async def write_actions(context, agent_session):
    while True:
        act = await agent_session._action_queue.get()
        msg = AgentActionReply()
        msg.action.content = act.SerializeToString()
        await context.write(msg)


class AgentServicer(AgentEndpointServicer):
    def __init__(self, agent_impls, cog_project):
        self.__impls = agent_impls
        self.__agent_sessions = {}
        self.__cog_project = cog_project
        atexit.register(self.__cleanup)

        logging.info("Agent Service started")

    async def Start(self, request, context):
        metadata = dict(context.invocation_metadata())

        actor_id = int(metadata["actor-id"])
        trial_id = metadata["trial-id"]
        key = _trial_key(trial_id, actor_id)

        if request.impl_name not in self.__impls:
            raise InvalidRequestError(
                message=f"Unknown agent impl: {request.impl_name}", request=request
            )
        impl = self.__impls[request.impl_name]

        self_info = request.actors_in_trial[actor_id]

        if self_info.actor_class not in self.__cog_project.actor_classes:
            raise InvalidRequestError(
                message=f"Unknown agent class: {request.actor_class}", request=request
            )
        actor_class = self.__cog_project.actor_classes[self_info.actor_class]

        if not _impl_can_serve_actor_class(impl, actor_class):
            raise InvalidRequestError(
                message=f"{request.impl_name} does not implement {request.actor_class}",
                request=request,
            )

        if key in self.__agent_sessions:
            raise InvalidRequestError(message="Agent already exists", request=request)

        trial = Trial(
            id_=metadata["trial-id"], cog_project=self.__cog_project, trial_config=None
        )
        new_session = _ServedActorSession(impl.impl, actor_class, trial, self_info.name)
        self.__agent_sessions[key] = new_session

        loop = asyncio.get_running_loop()
        new_session._task = loop.create_task(new_session._run())

        return AgentStartReply()

    async def End(self, request, context):
        key = _trial_key(context.meta_data["trial-id"], context.meta_data["actor-id"])

        return AgentEndReply()

    async def Decide(self, request_iterator, context):
        metadata = dict(context.invocation_metadata())
        key = _trial_key(metadata["trial-id"], metadata["actor-id"])
        agent_session = self.__agent_sessions[key]

        loop = asyncio.get_running_loop()
        reader_task = loop.create_task(
            read_observations(request_iterator, agent_session)
        )
        writer_task = loop.create_task(write_actions(context, agent_session))

        await agent_session._task

        reader_task.cancel()
        writer_task.cancel()

    async def Reward(self, request, context):
        return AgentRewardReply()

    async def Version(self, request, context):
        try:
            return list_versions()
        except Exception:
            traceback.print_exc()
            raise

    def __cleanup(self):
        for data in self.__agent_sessions.values():
            pass

        self.__agent_sessions.clear()

        atexit.unregister(self.__cleanup)

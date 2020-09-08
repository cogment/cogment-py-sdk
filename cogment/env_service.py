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

from abc import ABC, abstractmethod

from cogment.api.environment_pb2_grpc import EnvironmentEndpointServicer as Servicer
from cogment.api.environment_pb2_grpc import EnvironmentEndpointServicer

from cogment.api.environment_pb2 import (EnvStartRequest, EnvStartReply,
                                         EnvUpdateReply, EnvEndReply, ObservationSet, EnvOnMessageReply)
from cogment.api.common_pb2 import Feedback, ObservationData
from cogment.utils import list_versions

from types import SimpleNamespace, ModuleType
from typing import Any, Dict, Tuple

from cogment.environment import _ServedEnvironmentSession

from cogment.trial import Trial

import traceback
import atexit
import logging
import typing
import asyncio
from time import time


def new_actions_table(settings, trial):
    actions_by_actor_class = settings.ActionsTable(trial)
    actions_by_actor_id = actions_by_actor_class.all_actions()

    return actions_by_actor_class, actions_by_actor_id


def pack_observations(env_session, observations, reply):
    new_obs = [None] * len(env_session.trial.actors)

    for tgt, obs in observations:
        for actor_index, actor in enumerate(env_session.trial.actors):
            if isinstance(tgt, int):
                new_obs[actor_index] = obs
            elif tgt == "*" or tgt == '*.*':
                new_obs[actor_index] = obs
            elif isinstance(tgt, str):
                if "." not in tgt:
                    if actor.name == tgt:
                        new_obs[actor_index] = obs
                else:
                    class_name = tgt.split(".")
                    if class_name[1] == actor.name:
                        new_obs[actor_index] = obs
                    elif class_name[1] == "*":
                        if actor.actor_class.id_ == class_name[0]:
                            new_obs[actor_index] = obs

    snapshots = [True] * len(env_session.trial.actors)

    for actor_index, actor in enumerate(env_session.trial.actors):
        # if new_obs[actor_index] == None:
        if not new_obs[actor_index]:
            raise Exception("An actor is missing an observation")
        snapshots[actor_index] = isinstance(
            new_obs[actor_index], actor.actor_class.observation_space)

    # dupping time
    seen_observations = {}

    for actor_index, actor in enumerate(env_session.trial.actors):
        obs_id = id(new_obs[actor_index])
        obs_key = seen_observations.get(obs_id)
        if obs_key is None:
            obs_key = len(reply.observation_set.observations)

            reply.observation_set.observations.append(ObservationData(
                content=new_obs[actor_index].SerializeToString(),
                snapshot=snapshots[actor_index]
            ))

            seen_observations[obs_id] = obs_key

        reply.observation_set.actors_map.append(obs_key)


async def write_initial_observations(context, env_session):
    observations = await env_session._obs_queue.get()

    reply = EnvStartReply()
    reply.observation_set.tick_id = 0

    pack_observations(env_session, observations, reply)

    reply.observation_set.timestamp = int(time() * 1000000000)

    await context.write(reply)


async def write_observations(context, env_session):
    while True:
        observations = await env_session._obs_queue.get()

        reply = EnvUpdateReply()

        reply.feedbacks.extend(env_session.trial._gather_all_feedback())
        reply.messages.extend(env_session.trial._gather_all_messages(-1))

        reply.end_trial = env_session.end_trial
        reply.observation_set.tick_id = env_session.trial.tick_id

        pack_observations(env_session, observations, reply)

        reply.observation_set.timestamp = int(time() * 1000000000)

        await context.write(reply)


async def read_actions(request_iterator, env_session):
    async for request in request_iterator:
        len_actions = len(request.action_set.actions)
        len_actors = len(env_session.trial.actions_by_actor_id)
        if len_actions != len_actors:
            raise Exception(f"Received {len_actions} actions but have {len_actors} actors")

        for i, action in enumerate(env_session.trial.actions_by_actor_id):
            action.ParseFromString(request.action_set.actions[i])

        env_session._new_action(env_session.trial.actions)


class EnvironmentServicer(EnvironmentEndpointServicer):

    def __init__(self, env_impls, cog_project):
        self.__impls = env_impls
        self.__env_sessions = {}
        self.__cog_project = cog_project
        atexit.register(self.__cleanup)

        logging.info("Environment Service started")

    async def Start(self, request, context):
        metadata = dict(context.invocation_metadata())

        trial_id = metadata["trial-id"]
        key = trial_id

        if request.impl_name not in self.__impls:
            raise InvalidRequestError(message=f"Unknown agent impl: {request.impl_name}", request=request)
        impl = self.__impls[request.impl_name]

        env_class = self.__cog_project.env_class

        if key in self.__env_sessions:
            raise InvalidRequestError(
                message="Environment already exists", request=request)

        trial_config = None
        if request.HasField("trial_config"):
            if self.__cog_project.trial.config_type is None:
                raise Exception("trial config data but no config type")
            trial_config = self.__cog_project.trial.config_type()
            trial_config.ParseFromString(request.trial_config.content)

        trial = Trial(id_=metadata["trial-id"],
                      cog_project=self.__cog_project,
                      trial_config=trial_config)

        trial._add_actors(request.actors_in_trial)
        trial._add_actor_counts()
        trial._add_env()

        # action table time
        actions_by_actor_class, actions_by_actor_id = new_actions_table(
            self.__cog_project, trial)

        trial.actions = actions_by_actor_class
        trial.actions_by_actor_id = actions_by_actor_id

        new_session = _ServedEnvironmentSession(
            impl.impl, env_class, trial)
        self.__env_sessions[key] = new_session

        env_session = self.__env_sessions[key]

        loop = asyncio.get_running_loop()
        new_session._task = loop.create_task(new_session._run())

        await write_initial_observations(context, env_session)

    async def Update(self, request_iterator, context):

        metadata = dict(context.invocation_metadata())

        trial_id = metadata["trial-id"]
        key = trial_id

        env_session = self.__env_sessions[key]

        env_session.trial.tick_id += 1

        loop = asyncio.get_running_loop()
        reader_task = loop.create_task(
            read_actions(request_iterator, env_session))
        writer_task = loop.create_task(
            write_observations(context, env_session))

        await env_session._task

        reader_task.cancel()
        writer_task.cancel()

    async def OnMessage(self, request, context):
        metadata = dict(context.invocation_metadata())

        trial_id = metadata["trial-id"]
        key = trial_id

        env_session = self.__env_sessions[key]

        for message in request.messages:
            env_session._new_message(message)

        return EnvOnMessageReply()

    async def End(self, request, context):
        metadata = dict(context.invocation_metadata())

        trial_id = metadata["trial-id"]
        key = trial_id

        return EnvEndReply()

    def __cleanup(self):
        for data in self.__env_sessions.values():
            pass

        self.__env_sessions.clear()

        atexit.unregister(self.__cleanup)

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

from cogment.api.environment_pb2 import (
    EnvStartRequest,
    EnvStartReply,
    EnvUpdateReply,
    EnvEndReply,
    ObservationSet,
    EnvOnMessageReply,
)
from cogment.api.common_pb2 import Feedback, ObservationData, Observation
from cogment.utils import list_versions

from types import SimpleNamespace, ModuleType
from typing import Any, Dict, Tuple
import grpc.experimental.aio

from cogment.environment import _ServedEnvironmentSession

from cogment.trial import Trial

from prometheus_client import Summary, Counter

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


def pack_observations(env_session, observations, reply, tick_id):
    timestamp = int(time() * 1000000000)

    new_obs = [None] * len(env_session.trial.actors)

    for tgt, obs in observations:
        for actor_index, actor in enumerate(env_session.trial.actors):
            if isinstance(tgt, int):
                new_obs[actor_index] = obs
            elif tgt == "*" or tgt == "*.*":
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
        if not new_obs[actor_index]:
            raise Exception("An actor is missing an observation")
        snapshots[actor_index] = isinstance(
            new_obs[actor_index], actor.actor_class.observation_space
        )

    # dupping time
    seen_observations = {}

    for actor_index, actor in enumerate(env_session.trial.actors):
        obs_id = id(new_obs[actor_index])
        obs_key = seen_observations.get(obs_id)
        if obs_key is None:
            obs_key = len(reply.observation_set.observations)

            observation_data = ObservationData(
                content=new_obs[actor_index].SerializeToString(),
                snapshot=snapshots[actor_index],
            )

            reply.observation_set.observations.append(
                Observation(tick_id=tick_id, timestamp=timestamp, data=observation_data)
            )

            seen_observations[obs_id] = obs_key

        reply.observation_set.actors_map.append(obs_key)


async def write_observations(context, env_session):
    while True:
        observations, final = await env_session._obs_queue.get()

        reply = EnvUpdateReply(end_trial=final)

        reply.feedbacks.extend(env_session.trial._gather_all_feedback())
        reply.messages.extend(env_session.trial._gather_all_messages(-1))

        pack_observations(env_session, observations, reply, env_session.trial.tick_id)

        await context.write(reply)

        if final:
            break


async def read_actions(context, env_session):
    while True:
        request = await context.read()

        if request == grpc.experimental.aio.EOF:
            break

        if env_session._ignore_incoming_actions:
            # This is just leftover inflight actions after the trial has ended.
            continue

        len_actions = len(request.action_set.actions)
        len_actors = len(env_session.trial.actions_by_actor_id)

        if len_actions != len_actors:
            raise Exception(
                f"Received {len_actions} actions but have {len_actors} actors"
            )

        for i, action in enumerate(env_session.trial.actions_by_actor_id):
            action.ParseFromString(request.action_set.actions[i])

        env_session._new_action(env_session.trial.actions)


class EnvironmentServicer(EnvironmentEndpointServicer):
    def __init__(self, env_impls, cog_project):
        self.__impls = env_impls
        self.__env_sessions = {}
        self.__cog_project = cog_project

        self.UPDATE_REQUEST_TIME = Summary(
            "environment_update_processing_seconds",
            "Times spend by an environment on the update function",
            ["impl_name"],
        )
        self.TRAINING_DURATION = Summary(
            "environment_trial_duration", "Trial duration", ["trial_actor"]
        )
        self.TRIALS_STARTED = Counter(
            "environment_trials_started", "Number of trial starts", ["impl_name"]
        )
        self.TRIALS_ENDED = Counter(
            "environment_trials_ended", "Number of trial ends", ["impl_name"]
        )
        self.MESSAGES_RECEIVED = Counter(
            "environment_received_messages",
            "Number of messages received",
            ["impl_name"],
        )

        atexit.register(self.__cleanup)

        logging.info("Environment Service started")

    async def Start(self, request, context):
        metadata = dict(context.invocation_metadata())

        trial_id = metadata["trial-id"]
        key = trial_id

        target_impl = request.impl_name
        if not target_impl:
            target_impl = "default"

        if target_impl not in self.__impls:
            raise InvalidRequestError(
                message=f"Unknown env impl: {target_impl}", request=request
            )
        impl = self.__impls[target_impl]

        if key in self.__env_sessions:
            raise InvalidRequestError(
                message="Environment already exists", request=request
            )

        self.TRIALS_STARTED.labels(request.impl_name).inc()

        trial_config = None
        if request.HasField("trial_config"):
            if self.__cog_project.trial.config_type is None:
                raise Exception("trial config data but no config type")
            trial_config = self.__cog_project.trial.config_type()
            trial_config.ParseFromString(request.trial_config.content)

        trial = Trial(
            id_=metadata["trial-id"],
            cog_project=self.__cog_project,
            trial_config=trial_config,
        )

        trial._add_actors(request.actors_in_trial)
        trial._add_actor_counts()
        trial._add_env()

        # action table time
        actions_by_actor_class, actions_by_actor_id = new_actions_table(
            self.__cog_project, trial
        )

        trial.actions = actions_by_actor_class
        trial.actions_by_actor_id = actions_by_actor_id

        new_session = _ServedEnvironmentSession(impl.impl, trial, target_impl)
        self.__env_sessions[key] = new_session

        env_session = self.__env_sessions[key]

        loop = asyncio.get_running_loop()
        new_session._task = loop.create_task(new_session._run())

        observations, final = await env_session._obs_queue.get()

        reply = EnvStartReply()
        pack_observations(env_session, observations, reply, 0)

        return reply

    async def Update(self, request_iterator, context):

        metadata = dict(context.invocation_metadata())

        trial_id = metadata["trial-id"]
        key = trial_id

        env_session = self.__env_sessions[key]

        with self.UPDATE_REQUEST_TIME.labels(env_session.impl_name).time():
            env_session.trial.tick_id += 1

            # We are going to have three concurrent coroutines:
            # - One that reads actions from the orchestrator
            # - One that sends observations to the orchestrator
            # - The environment's main (which will be the current coroutine)
            loop = asyncio.get_running_loop()
            reader_task = loop.create_task(read_actions(context, env_session))
            writer_task = loop.create_task(write_observations(context, env_session))

            await env_session._task

            if not env_session.end_trial:
                del self.__env_sessions[key]
                raise Exception("Trial was never ended")

            env_session._ignore_incoming_actions = True

            await writer_task
            await reader_task

            del self.__env_sessions[key]

    async def OnMessage(self, request, context):
        metadata = dict(context.invocation_metadata())

        trial_id = metadata["trial-id"]
        key = trial_id

        env_session = self.__env_sessions[key]

        for message in request.messages:
            self.MESSAGES_RECEIVED.labels(env_session.impl_name).inc()
            env_session._new_message(message)

        return EnvOnMessageReply()

    async def End(self, request, context):

        metadata = dict(context.invocation_metadata())

        trial_id = metadata["trial-id"]
        key = trial_id

        env_session = self.__env_sessions[key]

        for idx, actor in enumerate(env_session.trial.actors):
            self.TRAINING_DURATION.labels(actor.name).observe(env_session.trial.tick_id)

        await env_session.end()

        self.TRIALS_ENDED.labels(env_session.impl_name).inc()

        self.__env_sessions.pop(key, None)

        return EnvEndReply()

    def __cleanup(self):
        for data in self.__env_sessions.values():
            pass

        self.__env_sessions.clear()

        atexit.unregister(self.__cleanup)

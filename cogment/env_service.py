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

from cogment.errors import InvalidRequestError
from cogment.api.environment_pb2_grpc import EnvironmentEndpointServicer

import cogment.api.environment_pb2 as env_api
from cogment.api.common_pb2 import Feedback, ObservationData, Observation
from cogment.utils import list_versions

from types import SimpleNamespace, ModuleType
from typing import Any, Dict, Tuple
import grpc.experimental.aio

from cogment.environment import _ServedEnvironmentSession, ENVIRONMENT_ACTOR_NAME

from cogment.trial import Trial

from prometheus_client import Summary, Counter

import atexit
import logging
import traceback
import typing
import asyncio
from time import time


def new_actions_table(settings, trial):
    actions_by_actor_class = settings.ActionsTable(trial)
    actions_by_actor_id = actions_by_actor_class.all_actions()

    return actions_by_actor_class, actions_by_actor_id


def pack_observations(env_session, observations, reply, tick_id):
    timestamp = int(time() * 1000000000)

    new_obs = [None] * len(env_session._trial.actors)

    for tgt, obs in observations:
        for actor_index, actor in enumerate(env_session._trial.actors):
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
                        if actor.actor_class.id == class_name[0]:
                            new_obs[actor_index] = obs

    snapshots = [True] * len(env_session._trial.actors)

    for actor_index, actor in enumerate(env_session._trial.actors):
        if not new_obs[actor_index]:
            raise Exception(f"Actor [{actor.name}] is missing an observation")
        snapshots[actor_index] = isinstance(new_obs[actor_index], actor.actor_class.observation_space)

    # dupping time
    seen_observations = {}

    reply.observation_set.tick_id = tick_id
    reply.observation_set.timestamp = timestamp

    for actor_index, actor in enumerate(env_session._trial.actors):
        actor_obs = new_obs[actor_index]
        obs_id = id(actor_obs)
        obs_key = seen_observations.get(obs_id)
        if obs_key is None:
            obs_key = len(reply.observation_set.observations)

            obs_content = actor_obs.SerializeToString()
            observation_data = ObservationData(content=obs_content, snapshot=snapshots[actor_index])
            reply.observation_set.observations.append(observation_data)

            seen_observations[obs_id] = obs_key

        reply.observation_set.actors_map.append(obs_key)


def _process_reply(observations, env_session):
    rep = env_api.EnvActionReply()

    rep.feedbacks.extend(env_session._trial._gather_all_feedback())
    rep.messages.extend(env_session._trial._gather_all_messages(ENVIRONMENT_ACTOR_NAME))
    pack_observations(env_session, observations, rep, env_session._trial.tick_id)

    return rep


async def write_observations(context, env_session):
    try:
        while True:
            observations, final = await env_session._retrieve_obs()

            reply = _process_reply(observations, env_session)
            reply.final_update = final
            await context.write(reply)

            if final:
                break

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


def _process_actions(request, env_session):
    len_actions = len(request.action_set.actions)
    len_actors = len(env_session._trial._actions_by_actor_id)

    if len_actions != len_actors:
        raise Exception(f"Received {len_actions} actions but have {len_actors} actors")

    for i, action in enumerate(env_session._trial._actions_by_actor_id):
        action.ParseFromString(request.action_set.actions[i])

    return env_session._trial._actions_by_actor_id


async def read_actions(context, env_session):
    try:
        while True:
            request = await context.read()

            if request == grpc.experimental.aio.EOF:
                break

            env_session._new_action(_process_actions(request, env_session))

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


class EnvironmentServicer(EnvironmentEndpointServicer):
    def __init__(self, env_impls, cog_settings, prometheus_registry):
        self.__impls = env_impls
        self.__env_sessions = {}
        self.__cog_settings = cog_settings

        self.UPDATE_REQUEST_TIME = Summary(
            "environment_update_processing_seconds",
            "Times spend by an environment on the update function",
            ["impl_name"],
            registry=prometheus_registry
        )
        self.TRAINING_DURATION = Summary(
            "environment_trial_duration", "Trial duration", ["trial_actor"],
            registry=prometheus_registry
        )
        self.TRIALS_STARTED = Counter(
            "environment_trials_started", "Number of trial starts", ["impl_name"],
            registry=prometheus_registry
        )
        self.TRIALS_ENDED = Counter(
            "environment_trials_ended", "Number of trial ends", ["impl_name"],
            registry=prometheus_registry
        )
        self.MESSAGES_RECEIVED = Counter(
            "environment_received_messages",
            "Number of messages received",
            ["impl_name"],
            registry=prometheus_registry
        )

        atexit.register(self.__cleanup)

        logging.info("Environment Service started")

    async def OnStart(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]

            if len(self.__impls) == 0:
                raise InvalidRequestError(message="No implementation registered", request=request)

            if request.impl_name:
                impl_name = request.impl_name
                impl = self.__impls.get(impl_name)
                if impl is None:
                    raise InvalidRequestError(message=f"Unknown environment impl [{impl_name}]", request=request)
            else:
                impl_name, impl = next(iter(self.__impls.items()))
                logging.info(f"Environment impl [{impl_name}] arbitrarily chosen")

            key = trial_id
            if key in self.__env_sessions:
                raise InvalidRequestError(message=f"Environment already exists for trial [{trial_id}]", request=request)

            self.TRIALS_STARTED.labels(impl_name).inc()

            trial = Trial(trial_id, request.actors_in_trial, self.__cog_settings)
            trial.tick_id = 0

            # action table time
            actions_by_actor_class, actions_by_actor_id = new_actions_table(self.__cog_settings, trial)

            trial._actions = actions_by_actor_class
            trial._actions_by_actor_id = actions_by_actor_id

            config = None
            if request.HasField("config"):
                if self.__cog_settings.environment.config_type is None:
                    raise Exception("Environment received config data of unknown type (was it defined in cogment.yaml)")
                config = self.__cog_settings.environment.config_type()
                config.ParseFromString(request.config.content)

            new_session = _ServedEnvironmentSession(impl.impl, trial, impl_name, config)
            self.__env_sessions[key] = new_session

            loop = asyncio.get_running_loop()
            new_session._task = loop.create_task(new_session._run())

            observations, _ = await new_session._retrieve_obs()

            reply = env_api.EnvStartReply()
            pack_observations(new_session, observations, reply, 0)

            return reply

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def OnAction(self, request_iterator, context):
        reader_task = None
        writer_task = None
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]

            key = trial_id
            env_session = self.__env_sessions[key]

            with self.UPDATE_REQUEST_TIME.labels(env_session.impl_name).time():
                env_session._trial.tick_id += 1

                # We are going to have three concurrent coroutines:
                # - One that reads actions from the orchestrator
                # - One that sends observations to the orchestrator
                # - The environment's main (which will be the current coroutine)
                loop = asyncio.get_running_loop()
                reader_task = loop.create_task(read_actions(context, env_session))
                writer_task = loop.create_task(write_observations(context, env_session))

                await env_session._task
                if not env_session._ended:
                    del self.__env_sessions[key]
                    raise Exception(f"Trial [{trial_id}] was never ended")

                del self.__env_sessions[key]

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

        finally:
            if reader_task is not None:
                reader_task.cancel()
            if writer_task is not None:
                writer_task.cancel()

    async def OnMessage(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]

            key = trial_id
            env_session = self.__env_sessions[key]

            for message in request.messages:
                self.MESSAGES_RECEIVED.labels(env_session.impl_name).inc()
                env_session._new_message(message)

            return env_api.EnvMessageReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def OnEnd(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]

            key = trial_id
            env_session = self.__env_sessions[key]

            for actor in env_session._trial.actors:
                self.TRAINING_DURATION.labels(actor.name).observe(env_session._trial.tick_id)

            obs = await env_session._end_request(_process_actions(request, env_session))

            if obs:
                reply = _process_reply(obs, env_session)
            else:
                reply = env_api.EnvActionReply()
            reply.set_end_trial(True)

            self.TRIALS_ENDED.labels(env_session.impl_name).inc()
            self.__env_sessions.pop(key, None)

            return reply

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    def __cleanup(self):
        self.__env_sessions.clear()
        atexit.unregister(self.__cleanup)

# Copyright 2021 AI Redefined Inc. <dev+cogment@ai-r.com>
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
import cogment.api.environment_pb2_grpc as grpc_api

import cogment.api.environment_pb2 as env_api
import cogment.api.common_pb2 as common_api
from cogment.utils import list_versions
from cogment.session import RecvEvent, RecvMessage, RecvAction, EventType

from types import SimpleNamespace, ModuleType
import grpc.aio  # type: ignore

from cogment.environment import _ServedEnvironmentSession

from cogment.trial import Trial

from prometheus_client import Summary, Counter

import atexit
import logging
import traceback
import typing
import asyncio
from time import time


def pack_observations(env_session, observations, reply, tick_id=-1):
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
                        if actor.actor_class.name == class_name[0]:
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
            observation_data = common_api.ObservationData(content=obs_content, snapshot=snapshots[actor_index])
            reply.observation_set.observations.append(observation_data)

            seen_observations[obs_id] = obs_key

        reply.observation_set.actors_map.append(obs_key)


def _process_reply(observations, env_session):
    rep = env_api.EnvActionReply()

    rep.rewards.extend(env_session._trial._gather_all_rewards())
    rep.messages.extend(env_session._trial._gather_all_messages())
    pack_observations(env_session, observations, rep)

    return rep


async def write_observations(context, env_session):
    try:
        while True:
            observations, final = await env_session._retrieve_obs()

            reply = _process_reply(observations, env_session)
            reply.final_update = final
            await context.write(reply)

            if final:
                env_session._trial.over = True
                env_session._new_event(RecvEvent(EventType.FINAL))
                break

    except asyncio.CancelledError as exc:
        logging.debug(f"Environment 'write_observations' coroutine cancelled: [{exc}]")

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


def _process_actions(request, env_session):
    env_session._trial.tick_id = request.action_set.tick_id

    len_actions = len(request.action_set.actions)
    len_actors = len(env_session._trial.actors)

    if len_actions != len_actors:
        raise Exception(f"Received {len_actions} actions but have {len_actors} actors")

    recv_event = RecvEvent(EventType.ACTIVE)
    for i, actor in enumerate(env_session._trial.actors):
        action = actor.actor_class.action_space()
        action.ParseFromString(request.action_set.actions[i])
        recv_event.actions.append(RecvAction(i, action))

    return recv_event


async def read_actions(context, env_session):
    try:
        while True:
            request = await context.read()

            if request == grpc.aio.EOF:
                logging.info(f"The orchestrator disconnected the environment")
                break

            env_session._new_event(_process_actions(request, env_session))

    except asyncio.CancelledError as exc:
        logging.debug(f"Environment 'read_actions' coroutine cancelled: [{exc}]")

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


class EnvironmentServicer(grpc_api.EnvironmentEndpointServicer):
    def __init__(self, env_impls, cog_settings, prometheus_registry=None):
        self.__impls = env_impls
        self.__env_sessions = {}
        self.__cog_settings = cog_settings

        self.update_count_per_trial = Summary(
            "environment_update_count_per_trial",
            "Number of update by trial",
            ["impl_name"],
            registry=prometheus_registry
        )
        self.trial_duration = Summary(
            "environment_trial_duration_in_second", "Trial duration", ["trial_actor"],
            registry=prometheus_registry
        )
        self.trials_started = Counter(
            "environment_trials_started", "Number of trial started", ["impl_name"],
            registry=prometheus_registry
        )
        self.trials_ended = Counter(
            "environment_trials_ended", "Number of trial ended", ["impl_name"],
            registry=prometheus_registry
        )
        self.messages_received = Counter(
            "environment_received_messages",
            "Number of messages received",
            ["impl_name"],
            registry=prometheus_registry
        )
        self.messages_sent = Counter(
            "environment_sent_messages",
            "Number of messages sent",
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

            self.trials_started.labels(impl_name).inc()

            trial = Trial(trial_id, request.actors_in_trial, self.__cog_settings)
            trial.tick_id = request.tick_id

            config = None
            if request.HasField("config"):
                if self.__cog_settings.environment.config_type is None:
                    raise Exception("Environment received config data of unknown type (was it defined in cogment.yaml)")
                config = self.__cog_settings.environment.config_type()
                config.ParseFromString(request.config.content)

            new_session = _ServedEnvironmentSession(impl.impl, trial, impl_name, config)
            self.__env_sessions[key] = new_session

            new_session._task = asyncio.create_task(new_session._run())

            observations, final = await new_session._retrieve_obs()
            if final:
                new_session._trial.over = True
                new_session._new_event(RecvEvent(EventType.FINAL))

            reply = env_api.EnvStartReply()
            pack_observations(new_session, observations, reply)

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

            # We are going to have three concurrent coroutines:
            # - One that reads actions from the orchestrator
            # - One that sends observations to the orchestrator
            # - The environment's main (which will be the current coroutine)
            reader_task = asyncio.create_task(read_actions(context, env_session))
            writer_task = asyncio.create_task(write_observations(context, env_session))

            with self.trial_duration.labels(env_session.impl_name).time():
                normal_return = await env_session._task

            self.update_count_per_trial.labels(env_session.impl_name).observe(env_session._trial.tick_id)

            if normal_return:
                if not env_session._last_event_received:
                    logging.warning(f"User environment implementation for [{env_session.name}]"
                                    f" running trial [{trial_id}] returned before end of trial")
                else:
                    logging.debug(f"User environment implementation for [{env_session.name}] returned")
            else:
                logging.debug(f"User environment implementation for [{env_session.name}] was cancelled")

            self.__env_sessions.pop(key, None)
            self.trials_ended.labels(env_session.impl_name).inc()

        except asyncio.CancelledError as exc:
            logging.debug(f"Environment [{env_session.name}] implementation coroutine cancelled: [{exc}]")
            raise

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
            env_session = self.__env_sessions.get(key)
            if env_session is None:
                logging.warning(f"Trial [{trial_id}] has ended or does not exist: "
                                f"[{len(request.messages)}] messages dropped")
                return env_api.EnvMessageReply()

            recv_event = RecvEvent(EventType.ACTIVE)
            for message in request.messages:
                recv_event.messages.append(RecvMessage(message))
                self.messages_received.labels(env_session.impl_name).inc()

            if recv_event.messages:
                env_session._new_event(recv_event)

            return env_api.EnvMessageReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def OnEnd(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]

            key = trial_id
            env_session = self.__env_sessions.get(key)
            if env_session is None:
                logging.warning(f"Trial [{trial_id}] has already ended or does not exist: cannot terminate")
                return env_api.EnvActionReply()

            event = _process_actions(request, env_session)
            event.type = EventType.ENDING
            obs = await env_session._end_request(event)

            env_session._trial.over = True
            env_session._new_event(RecvEvent(EventType.FINAL))

            if obs:
                reply = _process_reply(obs, env_session)
            else:
                reply = env_api.EnvActionReply()
            reply.final_update = True

            self.__env_sessions.pop(key, None)
            self.trials_ended.labels(env_session.impl_name).inc()

            return reply

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    def __cleanup(self):
        self.__env_sessions.clear()
        atexit.unregister(self.__cleanup)

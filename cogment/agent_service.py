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

import cogment.api.agent_pb2_grpc as grpc_api
import cogment.api.agent_pb2 as agent_api

from cogment.utils import list_versions
from cogment.trial import Trial

from cogment.errors import InvalidRequestError
from cogment.delta_encoding import DecodeObservationData
from cogment.actor import _ServedActorSession
from cogment.session import RecvEvent, RecvObservation, RecvMessage, RecvReward, EventType
import cogment.utils as utils

from prometheus_client import Summary, Counter, Gauge

from types import SimpleNamespace
import traceback
import atexit
import logging
import asyncio
import grpc.aio  # type: ignore


def _trial_key(trial_id, actor_name):
    return f"{trial_id}_{actor_name}"


def _impl_can_serve_actor_class(impl, actor_class):
    if impl.actor_classes:
        for ac in impl.actor_classes:
            if ac == actor_class.name:
                return True
        return False
    else:
        return True


async def read_observations(context, agent_session):
    try:
        while True:
            request = await context.read()

            if request == grpc.aio.EOF:
                logging.info(f"The orchestrator disconnected agent [{agent_session.name}]")
                break

            agent_session._trial.tick_id = request.observation.tick_id

            snapshot = DecodeObservationData(
                agent_session._actor_class,
                request.observation.data,
                agent_session._latest_observation,
            )
            agent_session._latest_observation = snapshot

            recv_event = RecvEvent(EventType.ACTIVE)
            recv_event.observation = RecvObservation(request.observation, snapshot)
            agent_session._new_event(recv_event)

    except asyncio.CancelledError:
        logging.debug(f"Agent [{agent_session.name}] 'read_observations' coroutine cancelled")

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


async def write_actions(context, agent_session):
    try:
        while True:
            act = await agent_session._retrieve_action()
            reply = agent_api.AgentActionReply()
            reply.action.tick_id = -1

            if act is not None:
                reply.action.content = act.SerializeToString()

            reply.rewards.extend(agent_session._trial._gather_all_rewards())
            reply.messages.extend(agent_session._trial._gather_all_messages())

            await context.write(reply)

    except asyncio.CancelledError:
        logging.debug(f"Agent [{agent_session.name}] 'write_action' coroutine cancelled")

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


class AgentServicer(grpc_api.AgentEndpointServicer):
    def __init__(self, agent_impls, cog_settings, prometheus_registry=None):
        self.__impls = agent_impls
        self.__agent_sessions = {}
        self.__cog_settings = cog_settings
        atexit.register(self.__cleanup)

        self.decide_request_time = Summary(
            "actor_decide_processing_seconds",
            "Time spent by an actor on the decide function",
            ["name", "impl_name"],
            registry=prometheus_registry
        )
        self.actors_started = Counter(
            "actor_started", "Number of actors created", ["impl_name"],
            registry=prometheus_registry
        )

        self.actors_ended = Counter(
            "actor_ended", "Number of actors ended", ["impl_name"],
            registry=prometheus_registry
        )
        self.messages_received = Counter(
            "actor_received_messages", "Number of messages received", ["name", "impl_name"],
            registry=prometheus_registry
        )
        self.rewards_received = Gauge(
            "actor_reward_summation", "Cumulative rewards received", ["name", "impl_name"],
            registry=prometheus_registry
        )
        self.rewards_counter = Counter(
            "actor_rewards_count", "Number of rewards received", ["name", "impl_name"],
            registry=prometheus_registry
        )

        logging.info("Agent Service started")

    async def OnStart(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            actor_name = str(metadata["actor-name"])
            trial_id = metadata["trial-id"]

            if len(self.__impls) == 0:
                raise InvalidRequestError(message="No implementation registered", request=request)

            if request.impl_name:
                impl = self.__impls.get(request.impl_name)
                if impl is None:
                    raise InvalidRequestError(message=f"Unknown agent impl [{request.impl_name}]", request=request)
            else:
                impl_name, impl = next(iter(self.__impls.items()))
                logging.info(f"Agent impl [{impl_name}] arbitrarily chosen for actor [{actor_name}]")

            self_info = None
            for info in request.actors_in_trial:
                if info.name == actor_name:
                    self_info = info
                    break
            if self_info is None:
                logging.debug(f"OnStart [{metadata}] request [{request}]")
                logging.debug(f"trial id [{trial_id}] agent name [{actor_name}]")
                raise InvalidRequestError(f"Unknown agent name [{actor_name}]", request=request)

            if self_info.actor_class not in self.__cog_settings.actor_classes:
                raise InvalidRequestError(
                    message=f"Unknown agent class [{request.actor_class}]", request=request
                )
            actor_class = self.__cog_settings.actor_classes[self_info.actor_class]

            if not _impl_can_serve_actor_class(impl, actor_class):
                raise InvalidRequestError(
                    message=f"[{request.impl_name}] does not implement [{request.actor_class}]",
                    request=request,
                )

            key = _trial_key(trial_id, actor_name)
            if key in self.__agent_sessions:
                raise InvalidRequestError(message="Agent already exists", request=request)

            self.actors_started.labels(request.impl_name).inc()

            trial = Trial(trial_id, request.actors_in_trial, self.__cog_settings)

            config = None
            if request.HasField("config"):
                if actor_class.config_type is None:
                    raise Exception(
                        f"Actor [{actor_name}] received config data of unknown type (was it defined in cogment.yaml?)")
                config = actor_class.config_type()
                config.ParseFromString(request.config.content)

            new_session = _ServedActorSession(
                impl.impl, actor_class, trial, self_info.name, request.impl_name, config
            )
            self.__agent_sessions[key] = new_session

            new_session._task = asyncio.create_task(new_session._run())

            return agent_api.AgentStartReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def OnEnd(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]
            actor_name = metadata["actor-name"]

            key = _trial_key(trial_id, actor_name)

            agent_session = self.__agent_sessions.get(key)
            if agent_session is not None:
                agent_session._trial.over = True
                data = request.final_data

                events = utils.decode_period_data(agent_session, data, EventType.ENDING)
                if events:
                    ordered_ticks = sorted(events)
                    agent_session._trial.tick_id = ordered_ticks[-1]

                    for tick_id in ordered_ticks:
                        evt = events.pop(tick_id)
                        agent_session._new_event(evt)

                agent_session._new_event(RecvEvent(EventType.FINAL))

                self.actors_ended.labels(agent_session.impl_name).inc()
            else:
                logging.error(f"Unknown trial id [{trial_id}] or actor name [{actor_name}] for end-of-trial")

            return agent_api.AgentEndReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def OnObservation(self, request_iterator, context):
        reader_task = None
        writer_task = None
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]
            actor_name = metadata["actor-name"]

            key = _trial_key(trial_id, actor_name)

            agent_session = self.__agent_sessions.get(key)
            if agent_session is not None:
                with self.decide_request_time.labels(agent_session.name, agent_session.impl_name).time():
                    reader_task = asyncio.create_task(read_observations(context, agent_session))
                    writer_task = asyncio.create_task(write_actions(context, agent_session))

                    normal_return = await agent_session._task

                    if normal_return:
                        if not agent_session._last_event_received:
                            logging.warning(f"User agent implementation for [{agent_session.name}]"
                                            " returned before required")
                        else:
                            logging.debug(f"User agent implementation for [{agent_session.name}] returned")
                    else:
                        logging.debug(f"User agent implementation for [{agent_session.name}] was cancelled")

                    del self.__agent_sessions[key]
            else:
                logging.error(f"Unknown trial id [{trial_id}] or actor name [{actor_name}] for observation")

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

        finally:
            if reader_task is not None:
                reader_task.cancel()
            if writer_task is not None:
                writer_task.cancel()

    async def OnReward(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]
            actor_name = metadata["actor-name"]

            if not request.reward.sources:
                logging.warning(f"Empty reward received for trial id [{trial_id}] and actor name [{actor_name}]")
                return agent_api.AgentRewardReply()

            key = _trial_key(trial_id, actor_name)
            agent_session = self.__agent_sessions.get(key)
            if agent_session is None:
                logging.error(f"Unknown trial id [{trial_id}] or actor name [{actor_name}] for reward."
                               " Was the user agent terminated before required?")
                return agent_api.AgentRewardReply()

            recv_event = RecvEvent(EventType.ACTIVE)
            recv_event.rewards = [RecvReward(request.reward)]
            agent_session._new_event(recv_event)

            value = recv_event.rewards[0].value
            self.rewards_counter.labels(agent_session.name, agent_session.impl_name).inc()
            if value < 0.0:
                self.rewards_received.labels(agent_session.name, agent_session.impl_name).dec(abs(value))
            else:
                self.rewards_received.labels(agent_session.name, agent_session.impl_name).inc(value)

            return agent_api.AgentRewardReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def OnMessage(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]
            actor_name = metadata["actor-name"]

            key = _trial_key(trial_id, actor_name)

            agent_session = self.__agent_sessions.get(key)
            if agent_session is not None:
                for message in request.messages:
                    recv_event = RecvEvent(EventType.ACTIVE)
                    recv_event.messages = [RecvMessage(message)]
                    agent_session._new_event(recv_event)
                    self.messages_received.labels(agent_session.name, agent_session.impl_name).inc()
            else:
                logging.error(f"Unknown trial id [{trial_id}] or actor name [{actor_name}] for message."
                               " Was the user agent terminated before required?")

            return agent_api.AgentMessageReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def Version(self, request, context):
        try:
            return list_versions()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    def __cleanup(self):
        self.__agent_sessions.clear()
        atexit.unregister(self.__cleanup)

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
import cogment.api.agent_pb2 as agent_api

from cogment.utils import list_versions
from cogment.trial import Trial

from cogment.errors import InvalidRequestError
from cogment.delta_encoding import DecodeObservationData
from cogment.actor import _ServedActorSession, Reward

from prometheus_client import Summary, Counter, Gauge

from types import SimpleNamespace
import traceback
import atexit
import logging
import typing
import asyncio
import grpc.experimental.aio


def _trial_key(trial_id, actor_name):
    return f"{trial_id}_{actor_name}"


def _impl_can_serve_actor_class(impl, actor_class):
    if impl.actor_classes:
        for ac in impl.actor_classes:
            if ac == actor_class.id:
                return True
        return False
    else:
        return True


async def read_observations(context, agent_session):
    try:
        while True:
            request = await context.read()

            # This means the GRPC channel has been closed by the orchestrator.
            if request == grpc.experimental.aio.EOF:
                break

            agent_session._trial.tick_id = request.observation.tick_id

            obs = DecodeObservationData(
                agent_session._actor_class,
                request.observation.data,
                agent_session._latest_observation,
            )
            agent_session._latest_observation = obs
            agent_session._new_observation(obs)

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


async def write_actions(context, agent_session):
    try:
        while True:
            act = await agent_session._retrieve_action()
            msg = agent_api.AgentActionReply()

            if act is not None:
                msg.action.content = act.SerializeToString()

            msg.feedbacks.extend(agent_session._trial._gather_all_feedback())

            actor_name = dict(context.invocation_metadata())["actor-name"]
            msg.messages.extend(agent_session._trial._gather_all_messages(actor_name))

            await context.write(msg)

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


class AgentServicer(AgentEndpointServicer):
    def __init__(self, agent_impls, cog_settings, prometheus_registry):
        self.__impls = agent_impls
        self.__agent_sessions = {}
        self.__cog_settings = cog_settings
        atexit.register(self.__cleanup)

        self.DECIDE_REQUEST_TIME = Summary(
            "actor_decide_processing_seconds",
            "Time spent by an actor on the decide function",
            ["name", "actor_class"],
            registry=prometheus_registry
        )
        self.ACTORS_STARTED = Counter(
            "actor_started", "Number of actors created", ["actor_class"],
            registry=prometheus_registry
        )

        self.ACTORS_ENDED = Counter(
            "actor_ended", "Number of actors ended", ["actor_class"],
            registry=prometheus_registry
        )
        self.MESSAGES_RECEIVED = Counter(
            "actor_received_messages", "Number of messages received", ["name", "actor_class"],
            registry=prometheus_registry
        )
        self.REWARDS_RECEIVED = Gauge(
            "actor_reward_summation", "Cumulative rewards received", ["name", "actor_class"],
            registry=prometheus_registry
        )
        self.REWARDS_COUNTER = Counter(
            "actor_rewards_count", "Number of rewards received", ["name", "actor_class"],
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

            self.ACTORS_STARTED.labels(request.impl_name).inc()

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

            loop = asyncio.get_running_loop()
            new_session._task = loop.create_task(new_session._run())

            return agent_api.AgentStartReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def OnEnd(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            key = _trial_key(metadata["trial-id"], metadata["actor-name"])
            agent_session = self.__agent_sessions[key]

            package = SimpleNamespace(observations=[], rewards=[], messages=[])
            for obs_request in request.final_data.observations:
                obs = DecodeObservationData(
                    agent_session._actor_class,
                    obs_request.data,
                    agent_session._latest_observation)
                agent_session._latest_observation = obs
                package.observations.append(obs)

            for rew_request in request.final_data.rewards:
                reward = Reward()
                reward._set_all(rew_request, -1)
                package.rewards.append(reward)

            for msg_request in request.final_data.messages:
                package.messages.append(msg_request)

            await agent_session._end(package)

            self.ACTORS_ENDED.labels(agent_session.impl_name).inc()

            self.__agent_sessions.pop(key, None)

            return agent_api.AgentEndReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def OnObservation(self, request_iterator, context):
        reader_task = None
        writer_task = None
        try:
            metadata = dict(context.invocation_metadata())
            key = _trial_key(metadata["trial-id"], metadata["actor-name"])

            agent_session = self.__agent_sessions[key]

            with self.DECIDE_REQUEST_TIME.labels(agent_session.name, agent_session.impl_name).time():
                loop = asyncio.get_running_loop()

                reader_task = loop.create_task(read_observations(context, agent_session))
                writer_task = loop.create_task(write_actions(context, agent_session))

                await agent_session._task

                del self.__agent_sessions[key]

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
            actor_name = str(metadata["actor-name"])
            trial_id = metadata["trial-id"]

            key = _trial_key(trial_id, actor_name)

            reward = Reward()
            reward._set_all(request.reward, request.tick_id)

            agent_session = self.__agent_sessions.get(key)
            if agent_session is not None:
                self.REWARDS_COUNTER.labels(agent_session.name, agent_session.impl_name).inc()
                if reward.value < 0.0:
                    self.REWARDS_RECEIVED.labels(agent_session.name, agent_session.impl_name).dec(abs(reward.value))
                else:
                    self.REWARDS_RECEIVED.labels(agent_session.name, agent_session.impl_name).inc(reward.value)

                agent_session._new_reward(reward)
            else:
                logging.error(f"Uknown trial id {trial_id} or/and actor name {actor_name}.")

            return agent_api.AgentRewardReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def OnMessage(self, request, context):
        try:
            metadata = dict(context.invocation_metadata())
            actor_name = str(metadata["actor-name"])
            trial_id = metadata["trial-id"]

            key = _trial_key(trial_id, actor_name)

            agent_session = self.__agent_sessions[key]

            for message in request.messages:
                agent_session._new_message(message)
                self.MESSAGES_RECEIVED.labels(agent_session.name, agent_session.impl_name).inc()

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

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
from traceback import print_exc
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
                agent_session.actor_class,
                request.observation.data,
                agent_session._latest_observation,
            )
            agent_session._latest_observation = obs
            agent_session._new_observation(obs)
    except Exception as e:
        print_exc()
        raise e


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
    except Exception as e:
        print_exc()
        raise e


class AgentServicer(AgentEndpointServicer):
    def __init__(self, agent_impls, cog_settings, prometheus_registry):
        self.__impls = agent_impls
        self.__agent_sessions = {}
        self.__cog_settings = cog_settings
        atexit.register(self.__cleanup)

        self.DECIDE_REQUEST_TIME = Summary(
            "actor_decide_processing_seconds",
            "Time spent by an actor on the decide function",
            ["name"],
            registry=prometheus_registry
        )
        self.ACTORS_STARTED = Counter(
            "actor_started", "Number of actors created", ["impl_name"],
            registry=prometheus_registry
        )
        self.ACTORS_ENDED = Counter(
            "actor_ended", "Number of actors ended", ["impl_name"],
            registry=prometheus_registry
        )
        self.MESSAGES_RECEIVED = Counter(
            "actor_received_messages", "Number of messages received", ["name"],
            registry=prometheus_registry
        )
        self.REWARDS_RECEIVED = Gauge(
            "actor_reward_summation", "Cumulative rewards received", ["name"],
            registry=prometheus_registry
        )

        logging.info("Agent Service started")

    async def OnStart(self, request, context):
        metadata = dict(context.invocation_metadata())
        actor_name = str(metadata["actor-name"])
        trial_id = metadata["trial-id"]

        key = _trial_key(trial_id, actor_name)

        if request.impl_name not in self.__impls:
            raise InvalidRequestError(
                message=f"Unknown agent impl: {request.impl_name}", request=request
            )
        impl = self.__impls[request.impl_name]

        self_info = None
        for info in request.actors_in_trial:
            if info.name == actor_name:
                self_info = info
                break
        if self_info is None:
            raise InvalidRequestError(f"Unknown agent name: {actor_name}", request=request)

        if self_info.actor_class not in self.__cog_settings.actor_classes:
            raise InvalidRequestError(
                message=f"Unknown agent class: {request.actor_class}", request=request
            )
        actor_class = self.__cog_settings.actor_classes[self_info.actor_class]

        if not _impl_can_serve_actor_class(impl, actor_class):
            raise InvalidRequestError(
                message=f"{request.impl_name} does not implement {request.actor_class}",
                request=request,
            )

        if key in self.__agent_sessions:
            raise InvalidRequestError(message="Agent already exists", request=request)

        self.ACTORS_STARTED.labels(request.impl_name).inc()

        trial = Trial(trial_id, request.actors_in_trial, self.__cog_settings)

        config = None
        if request.HasField("config"):
            if actor_class.config_type is None:
                raise Exception(
                    f"Actor [{actor_name}] received config data of unknown type (was it defined in cogment.yaml)")
            config = actor_class.config_type()
            config.ParseFromString(request.config.content)

        new_session = _ServedActorSession(
            impl.impl, actor_class, trial, self_info.name, request.impl_name, config
        )
        self.__agent_sessions[key] = new_session

        loop = asyncio.get_running_loop()
        new_session._task = loop.create_task(new_session._run())

        return agent_api.AgentStartReply()

    async def OnEnd(self, request, context):
        metadata = dict(context.invocation_metadata())
        key = _trial_key(metadata["trial-id"], metadata["actor-name"])
        agent_session = self.__agent_sessions[key]

        package = SimpleNamespace(observations=[], rewards=[], messages=[])
        for obs_request in request.final_data.observations:
            obs = DecodeObservationData(
                agent_session.actor_class,
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

    async def OnObservation(self, request_iterator, context):
        metadata = dict(context.invocation_metadata())
        key = _trial_key(metadata["trial-id"], metadata["actor-name"])

        agent_session = self.__agent_sessions[key]

        with self.DECIDE_REQUEST_TIME.labels(agent_session.name).time():
            loop = asyncio.get_running_loop()

            reader_task = loop.create_task(read_observations(context, agent_session))
            writer_task = loop.create_task(write_actions(context, agent_session))

            await agent_session._task

            reader_task.cancel()
            writer_task.cancel()

            del self.__agent_sessions[key]

    async def OnReward(self, request, context):
        metadata = dict(context.invocation_metadata())
        actor_name = str(metadata["actor-name"])
        trial_id = metadata["trial-id"]

        key = _trial_key(trial_id, actor_name)

        reward = Reward()
        reward._set_all(request.reward, request.tick_id)

        agent_session = self.__agent_sessions[key]
        if reward.value < 0.0:
            self.REWARDS_RECEIVED.labels(agent_session.name).dec(abs(reward.value))
        else:
            self.REWARDS_RECEIVED.labels(agent_session.name).inc(reward.value)

        agent_session._new_reward(reward)

        return agent_api.AgentRewardReply()

    async def OnMessage(self, request, context):
        metadata = dict(context.invocation_metadata())
        actor_name = str(metadata["actor-name"])
        trial_id = metadata["trial-id"]

        key = _trial_key(trial_id, actor_name)

        agent_session = self.__agent_sessions[key]

        for message in request.messages:
            agent_session._new_message(message)
            self.MESSAGES_RECEIVED.labels(agent_session.name).inc()

        return agent_api.AgentMessageReply()

    async def Version(self, request, context):
        try:
            return list_versions()
        except Exception:
            traceback.print_exc()
            raise

    def __cleanup(self):
        self.__agent_sessions.clear()
        atexit.unregister(self.__cleanup)

from cogment.api.agent_pb2_grpc import AgentEndpointServicer

from cogment.api.agent_pb2 import (
    AgentStartReply, AgentRewardReply, AgentEndReply, AgentActionReply, AgentOnMessageReply)

from cogment.utils import list_versions
from cogment.trial import Trial

from cogment.errors import InvalidRequestError
from cogment.delta_encoding import DecodeObservationData
from cogment.actor import _ServedActorSession

from prometheus_client import Summary, Counter, Gauge

import traceback
import atexit
import logging
import typing
import asyncio


def _trial_key(trial_id, actor_id):
    return f'{trial_id}_{actor_id}'


def _impl_can_serve_actor_class(impl, actor_class):
    if isinstance(impl.actor_class, typing.List):
        return any(__impl_can_serve_actor_class(e) for e in impl.actor_class)

    return impl.actor_class == "*" or impl.actor_class == actor_class.id_


async def read_observations(context, agent_session):
    while True:
        request = await context.read()
        obs = DecodeObservationData(
            agent_session.actor_class,
            request.observation.data,
            agent_session.latest_observation
        )
        print(request)
        agent_session._new_observation(obs, request.final)
 
async def write_actions(context, agent_session):
    while True:
        act = await agent_session._action_queue.get()
        msg = AgentActionReply()
        msg.action.content = act.SerializeToString()

        msg.feedbacks.extend(agent_session.trial._gather_all_feedback())

        msg.messages.extend(agent_session.trial._gather_all_messages(
            int(dict(context.invocation_metadata())["actor-id"])))

        await context.write(msg)


class AgentServicer(AgentEndpointServicer):

    def __init__(self, agent_impls, cog_project):
        self.__impls = agent_impls
        self.__agent_sessions = {}
        self.__cog_project = cog_project
        atexit.register(self.__cleanup)

        self.DECIDE_REQUEST_TIME = Summary(
            'actor_decide_processing_seconds', 'Time spent by an actor on the decide function', ['name'])
        self.ACTORS_STARTED = Counter(
            'actors_started', 'Number of actors created', ['impl_name'])
        self.ACTORS_ENDED = Counter(
            'actors_ended', 'Number of actors ended', ['impl_name'])
        self.MESSAGES_RECEIVED = Counter(
            'actor_received_messages', 'Number of messages received', ['name'])
        self.REWARDS_RECEIVED = Gauge(
            'actor_reward_summation', 'Cumulative rewards received', ['name'])

        logging.info("Agent Service started")

    async def Start(self, request, context):
        metadata = dict(context.invocation_metadata())

        actor_id = int(metadata["actor-id"])
        trial_id = metadata["trial-id"]
        key = _trial_key(trial_id, actor_id)

        if request.impl_name not in self.__impls:
            raise InvalidRequestError(message=f"Unknown agent impl: {request.impl_name}", request=request)
        impl = self.__impls[request.impl_name]

        self_info = request.actors_in_trial[actor_id]

        if self_info.actor_class not in self.__cog_project.actor_classes:
            raise InvalidRequestError(message=f"Unknown agent class: {request.actor_class}", request=request)
        actor_class = self.__cog_project.actor_classes[self_info.actor_class]

        if not _impl_can_serve_actor_class(impl, actor_class):
            raise InvalidRequestError(message=f"{request.impl_name} does not implement {request.actor_class}",
                                      request=request)

        if key in self.__agent_sessions:
            raise InvalidRequestError(
                message="Agent already exists", request=request)

        self.ACTORS_STARTED.labels(request.impl_name).inc()

        trial = Trial(id_=metadata["trial-id"],
                      cog_project=self.__cog_project,
                      trial_config=None)

        trial._add_actors(request.actors_in_trial)
        trial._add_env()

        new_session = _ServedActorSession(
            impl.impl, actor_class, trial, self_info.name, request.impl_name)
        self.__agent_sessions[key] = new_session

        loop = asyncio.get_running_loop()
        new_session._task = loop.create_task(new_session._run())

        return AgentStartReply()

    async def End(self, request, context):
        metadata = dict(context.invocation_metadata())
        key = _trial_key(metadata["trial-id"],
                         metadata["actor-id"])
        agent_session = self.__agent_sessions[key]

        await agent_session.end()

        self.ACTORS_ENDED.labels(agent_session.impl_name).inc()

        self.__agent_sessions.pop(key, None)

        return AgentEndReply()

    async def Decide(self, request_iterator, context):
        metadata = dict(context.invocation_metadata())
        key = _trial_key(metadata["trial-id"],
                         metadata["actor-id"])

        agent_session = self.__agent_sessions[key]

        with self.DECIDE_REQUEST_TIME.labels(agent_session.name).time():
            loop = asyncio.get_running_loop()

            reader_task = loop.create_task(
                read_observations(context, agent_session))
            writer_task = loop.create_task(
                write_actions(context, agent_session))

            await agent_session._task

            print("actor main task over")
            reader_task.cancel()
            writer_task.cancel()


            del self.__agent_sessions[key]

    async def Reward(self, request, context):
        metadata = dict(context.invocation_metadata())

        actor_id = int(metadata["actor-id"])
        trial_id = metadata["trial-id"]
        key = _trial_key(trial_id, actor_id)

        agent_session = self.__agent_sessions[key]

        agent_session._new_reward(request.reward)

        if request.reward.value < 0.0:
            self.REWARDS_RECEIVED.labels(agent_session.name).dec(
                abs(request.reward.value))
        else:
            self.REWARDS_RECEIVED.labels(
                agent_session.name).inc(request.reward.value)

        return AgentRewardReply()

    async def OnMessage(self, request, context):
        metadata = dict(context.invocation_metadata())

        actor_id = int(metadata["actor-id"])
        trial_id = metadata["trial-id"]
        key = _trial_key(trial_id, actor_id)

        agent_session = self.__agent_sessions[key]

        for message in request.messages:
            agent_session._new_message(message)
            self.MESSAGES_RECEIVED.labels(agent_session.name).inc()

        return AgentOnMessageReply()

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

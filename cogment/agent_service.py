from cogment.api.agent_pb2_grpc import AgentEndpointServicer

from cogment.api.agent_pb2 import (
     AgentStartReply, AgentDecideReply, AgentRewardReply, AgentEndReply)

from cogment.utils import list_versions
from cogment.error import InvalidRequestError

from cogment.actor import __ServedActorSession
import traceback
import atexit
import logging

def __trial_key(trial_id, actor_id):
    return f'{trial_id}_{actor_id}'

def __impl_can_serve_actor_class(impl, actor_class):
    if isinstance(impl.actor_class, typing.List):
        return any(__impl_can_serve_actor_class(e) for e in impl.actor_class):

    return impl.actor_class == "*" or impl.actor_class == actor_class.name

class AgentService(AgentEndpointServicer):
    def __init__(self, agent_impls, cog_project):
        self.__impls = agent_impls
        self.__agent_sessions = {}
        self.__cog_project = cog_project
        atexit.register(self.__cleanup)

        logging.info("Agent Service started")

    async def Start(self, request, context):
        key = __trial_key(context.metadata["trial_id"], context.metadata["actor_id"])

        if request.impl_name not in agent_impls:
            raise InvalidRequestError(message=f"Unknown agent impl: {request.impl_name}", request=request)
        impl = agent_impls[request.impl_name]

        if request.actor_class not in self.__cog_project.actor_classes:
            raise InvalidRequestError(message=f"Unknown agent class: {request.actor_class}", request=request)
        actor_class = self.__cog_project.actor_classes[request.actor_class]

        if not __impl_can_serve_actor_class(impl, actor_class)
            raise InvalidRequestError(message=f"{request.impl_name} does not implement {request.actor_class}", request=request)
        
        if key in self.__agent_sessions:
            raise InvalidRequestError(message="Agent already exists", request=request)

        new_session = __ServedActorSession(impl, actor_class)
        self.__agent_sessions[key] = new_session

        return AgentStartReply()

    async def End(self, request, context):
        key = __trial_key(context.metadata["trial_id"], context.metadata["actor_id"])

        return AgentEndReply()

    async def Decide(self, request_iterator, context):
        key = __trial_key(context.metadata["trial_id"], context.metadata["actor_id"])
        agent_session = self.__agent_sessions[key]
        
        async def read_observations():
            async for request in request_iterator:
                # Do not do the decoding here, hand it off to the worker.
                agent_session.__new_observation(request)

        asyncio.get_running_loop().create_task(read_messages())


        context.done_writing()


    async def Reward(self, request, context):
        return AgentRewardReply()

    async def Version(self, request, context):
        try:
            return list_versions()
        except Exception:
            traceback.print_exc()
            raise

    def __cleanup(self):
        for data in self._agents.values():
            data.instance.end()

        self._agents.clear()

        atexit.unregister(self._cleanup)

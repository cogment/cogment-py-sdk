from cogment.api.agent_pb2_grpc import AgentEndpointServicer

from cogment.api.agent_pb2 import (
     AgentStartReply, AgentDecideReply, AgentRewardReply, AgentEndReply)

from cogment.utils import list_versions
from cogment.error import InvalidRequestError

import traceback
import atexit
import logging

def __trial_key(trial_id, actor_id):
    return f'{trial_id}_{actor_id}'

class AgentService(AgentEndpointServicer):
    def __init__(self, agent_impls):
        self.__impls = agent_impls
        atexit.register(self.__cleanup)

        logging.info("Agent Service started")

    def Start(self, request, context):
        if request.impl_name not in agent_impls:
            raise InvalidRequestError(message="Unknown agent impl", request=request)

        return AgentStartReply()

    def End(self, request, context):
        return AgentEndReply()

    def Decide(self, request, context):
        return AgentDecideReply()

    def Reward(self, request, context):
        return AgentRewardReply()

    def Version(self, request, context):
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

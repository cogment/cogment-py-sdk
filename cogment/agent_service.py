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

from cogment.api.agent_pb2 import (
    AgentStartReply,
    AgentDecideReply,
    AgentRewardReply,
    AgentEndReply,
)

from cogment.utils import list_versions
from cogment.error import InvalidRequestError

import traceback
import atexit
import logging


def __trial_key(trial_id, actor_id):
    return f"{trial_id}_{actor_id}"


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

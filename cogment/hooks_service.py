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

import traceback

from types import SimpleNamespace
from typing import Dict

from cogment.api.hooks_pb2_grpc import TrialHooksServicer as Servicer
from cogment.api.hooks_pb2_grpc import TrialHooksServicer
from cogment.api.hooks_pb2 import TrialContext
from cogment.api.common_pb2 import TrialParams
from cogment.utils import list_versions, raw_params_to_user_params

import atexit
import logging
import asyncio


def _user_params_to_raw_params(params, settings):
    result = TrialParams()

    result.max_steps = params.max_steps
    result.max_inactivity = params.max_inactivity

    if params.trial_config is not None:
        result.trial_config.content = params.trial_config.SerializeToString()

    result.environment.endpoint = params.environment.endpoint
    if params.environment.config is not None:
        result.environment.config.content = \
            params.environment.config.SerializeToString()

    for a in params.actors:
        actor_pb = result.actors.add()
        actor_pb.actor_class = a.actor_class
        actor_pb.endpoint = a.endpoint
        if a.config is not None:
            actor_pb.config.content = a.config.SerializeToString()

    return result


class PrehookServicer(TrialHooksServicer):

    def __init__(self, prehook_impls, cog_project):

        self.__impls = prehook_impls
        self.__cog_project = cog_project

        logging.info("Prehook Service started")

    async def PreTrial(self, request, context):

        user_params = raw_params_to_user_params(request.params,
                                                self.__cog_project)

        for impl in self.__impls:

            user_params = await impl(user_params)

        reply = TrialContext()
        reply.CopyFrom(request)

        reply.params.CopyFrom(_user_params_to_raw_params(user_params,
                                                         self.__cog_project))

        return reply

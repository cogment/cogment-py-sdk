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

from types import SimpleNamespace

from cogment.api.hooks_pb2_grpc import TrialHooksServicer
from cogment.api.hooks_pb2 import TrialContext
import cogment.utils as utils
from cogment.trial import Trial
from cogment.prehook import _ServedPrehookSession

import logging


class PrehookServicer(TrialHooksServicer):

    def __init__(self, impls, cog_project):

        self.__impls = impls
        self.__cog_project = cog_project

        logging.info("Prehook Service started")

    async def PreTrial(self, request, context):
        metadata = dict(context.invocation_metadata())
        trial_id = metadata["trial-id"]
        trial = Trial(trial_id, self.__cog_project)

        user_params = utils.raw_params_to_user_params(request.params, self.__cog_project)

        prehook = _ServedPrehookSession(user_params, trial)
        for impl in self.__impls:
            await impl(prehook)
            prehook._recode()

        reply = TrialContext()
        reply.CopyFrom(request)
        reply.params.CopyFrom(utils.user_params_to_raw_params(prehook._params, self.__cog_project))
        return reply

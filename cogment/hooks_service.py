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

from types import SimpleNamespace

import cogment.api.hooks_pb2_grpc as grpc_api
import cogment.api.hooks_pb2 as hooks_api
import cogment.utils as utils
from cogment.trial import Trial
from cogment.prehook import PrehookSession
from cogment.errors import CogmentError

import logging
import asyncio


class PrehookServicer(grpc_api.TrialHooksSPServicer):

    def __init__(self, impl, cog_settings, prometheus_registry=None):

        self.__impl = impl
        self.__cog_settings = cog_settings

        logging.info("Prehook Service started")

    # Override
    async def OnPreTrial(self, request, context):
        if not self.__impl:
            logging.warning("No implementation registered on prehook request")
            raise CogmentError("No implementation registered")

        try:
            metadata = dict(context.invocation_metadata())
            logging.debug(f"Received metadata: [{metadata}]")
            trial_id = metadata["trial-id"]
            user_id = metadata["user-id"]

            trial = Trial(trial_id, [], self.__cog_settings)
            user_params = utils.raw_params_to_user_params(request.params, self.__cog_settings)

            prehook = PrehookSession(user_params, trial, user_id)
            try:
                await self.__impl(prehook)

            except asyncio.CancelledError as exc:
                logging.debug(f"Prehook implementation coroutine cancelled: [{exc}]")
                return False

            except Exception:
                logging.exception(f"An exception occured in user prehook implementation:")
                raise

            prehook._recode()

            reply = hooks_api.PreTrialParams()
            reply.params.CopyFrom(utils.user_params_to_raw_params(prehook._params, self.__cog_settings))
            return reply

        except Exception:
            logging.exception("OnPreTrial")
            raise

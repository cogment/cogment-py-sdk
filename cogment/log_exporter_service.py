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

import cogment.api.datalog_pb2_grpc as grpc_api
import cogment.api.datalog_pb2 as datalog_api
from cogment.trial import Trial
from cogment.datalog import _ServedDatalogSession
from cogment.utils import raw_params_to_user_params, list_versions
import logging
import traceback
import asyncio


class LogExporterService(grpc_api.LogExporterServicer):

    def __init__(self, impl, cog_settings):
        self.__impl = impl
        self.__cog_settings = cog_settings
        logging.info("Log Exporter Service started")

    async def OnLogSample(self, request_iterator, context):
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]

            trial = Trial(trial_id, [], self.__cog_settings)

            msg = await request_iterator.__anext__()
            assert msg.HasField("trial_params")
            trial_params = raw_params_to_user_params(msg.trial_params, self.__cog_settings)

            session = _ServedDatalogSession(self.__impl, trial, trial_params)
            loop = asyncio.get_running_loop()
            session._task = loop.create_task(session._run())

            # TODO: Wait for session._started
            async for msg in request_iterator:
                if session._task.done():
                    break
                assert msg.HasField("sample")
                session._new_sample(msg.sample)

            if not session._task.done():
                session._end()

            return datalog_api.LogExporterSampleReply()

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

    async def Version(self, request, context):
        try:
            return list_versions()
        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

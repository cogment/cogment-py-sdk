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

import cogment.api.common_pb2 as common_api
import cogment.api.datalog_pb2_grpc as grpc_api
import cogment.api.datalog_pb2 as datalog_api
from cogment.trial import Trial
from cogment.datalog import _ServedDatalogSession
from cogment.utils import raw_params_to_user_params, list_versions
import logging
import traceback
import asyncio

import grpc.aio  # type: ignore


async def read_sample(context, session):
    try:
        while True:
            request = await context.read()

            if request == grpc.aio.EOF:
                logging.info(f"The orchestrator disconnected from LogExpoterService.")
                break

            elif request.HasField("sample"):
                trial_ended = (request.sample.trial_data.state == common_api.TrialState.ENDED)
                session._new_sample(request.sample)
                if trial_ended:
                    break
            else:
                logging.warning(f"Invalid request received from the orchestrator : {request}")

    except asyncio.CancelledError:
        logging.debug(f"LogExporterService 'read_sample' coroutine cancelled.")

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise

    # Exit the loop
    session._new_sample(None)


class LogExporterService(grpc_api.LogExporterServicer):
    def __init__(self, impl, cog_settings):
        self._impl = impl
        self.__cog_settings = cog_settings
        logging.info("Log Exporter Service started")

    async def OnLogSample(self, request_iterator, context):
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]

            request = await context.read()

            if not request.HasField("trial_params"):
                raise Exception(f"Initial logging request for [{trial_id}] does not contain parameters.")

            trial_params = raw_params_to_user_params(request.trial_params, self.__cog_settings)
            raw_trial_params = request.trial_params

            session = _ServedDatalogSession(self._impl, trial_id, trial_params, raw_trial_params)
            session._task = asyncio.create_task(session._run())

            reader_task = asyncio.create_task(read_sample(context, session))

            # TODO: Investigate probable bug in easy_grpc that expects a stream to be "used"
            reply = datalog_api.LogExporterSampleReply()
            await context.write(reply)

            normal_return = await session._task

            if normal_return:
                logging.debug(f"User datalog implementation returned")
            else:
                logging.debug(f"User datalog implementation was cancelled")

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

        finally:
            if reader_task is not None:
                reader_task.cancel()

    async def Version(self, request, context):
        try:
            return list_versions()
        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

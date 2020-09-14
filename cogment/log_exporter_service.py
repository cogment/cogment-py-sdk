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

from cogment.api.data_pb2_grpc import LogExporterServicer

from cogment.api.data_pb2 import LogReply

# from cogment.hooks_service import _raw_params_to_user_params
from cogment.utils import raw_params_to_user_params

from cogment.errors import InvalidRequestError

import traceback
import atexit
import logging
import typing
import asyncio

import sys


class LogExporterService(LogExporterServicer):

    def __init__(self, datalog_impls, cog_project):
        self.__impls = datalog_impls
        self.__cog_project = cog_project

        logging.info("Log Exporter Service started")

    async def Log(self, request_iterator, context):
        metadata = dict(context.invocation_metadata())

        trial_id = metadata["trial-id"]

        msg = await request_iterator.__anext__()
        assert msg.HasField("trial_params")
        trial_params = raw_params_to_user_params(
            msg.trial_params, self.__cog_project)

        async def extract_samples(req):
            async for msg in req:
                assert msg.HasField("sample")
                yield msg.sample

        samples = extract_samples(request_iterator)

        await self.__impls(samples, trial_params, trial_id)

        return LogReply()

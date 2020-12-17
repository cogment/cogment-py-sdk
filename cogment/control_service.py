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

import logging
import traceback
import grpc
import grpc.experimental.aio

import cogment.api.orchestrator_pb2 as orchestrator
from cogment.api.orchestrator_pb2_grpc import TrialLifecycleStub
from cogment.trial import Trial
from cogment.control import _ServedControlSession


class ControlServicer:
    def __init__(self, cog_settings, endpoint):
        self.cog_settings = cog_settings
        channel = grpc.experimental.aio.insecure_channel(endpoint)
        self.lifecycle_stub = TrialLifecycleStub(channel)

    async def run(self, user_id, impl, trial_config):
        req = orchestrator.TrialStartRequest()
        req.user_id = user_id
        if trial_config is not None:
            req.config.content = trial_config.SerializeToString()

        # TODO: after the next line the process hangs indefinitely when running two integration tests
        rep = await self.lifecycle_stub.StartTrial(req)
        trial = Trial(rep.trial_id, rep.actors_in_trial, self.cog_settings)

        try:
            await impl(_ServedControlSession(trial, self.lifecycle_stub))
        except Exception:
            logging.error(f"An exception occured in user control implementation:\n{traceback.format_exc()}")
            raise

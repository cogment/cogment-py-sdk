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

import grpc
import grpc.experimental.aio

from cogment.api.orchestrator_pb2_grpc import TrialLifecycleStub, ActorEndpointStub
from cogment.api.orchestrator_pb2 import TrialStartRequest, TerminateTrialRequest
from cogment.trial import TrialLifecycle


class Connection:
    def __init__(self, cog_project, endpoint):
        self.cog_project = cog_project

        # channel = grpc.insecure_channel(endpoint)
        channel = grpc.experimental.aio.insecure_channel(endpoint)

        self.__lifecycle_stub = TrialLifecycleStub(channel)
        self.__actor_stub = ActorEndpointStub(channel)

    async def start_trial(self, trial_config, user_id):
        req = TrialStartRequest()
        req.config.content = trial_config.SerializeToString()
        req.user_id = user_id

        rep = await self.__lifecycle_stub.StartTrial(req)

        # added trial_config to following and in trial.py TrialLifecycle
        return TrialLifecycle(rep.trial_id, trial_config, rep.actors_in_trial, self)

    async def terminate(self, trial_id):
        req = TerminateTrialRequest()

        await self.__lifecycle_stub.TerminateTrial(
            req, metadata=(("trial-id", trial_id),)
        )

    def join_trial(self, trial_id, actor_id, actor_class, impl):
        pass

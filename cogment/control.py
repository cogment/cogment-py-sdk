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

import cogment.api.orchestrator_pb2 as orchestrator_api

from abc import ABC, abstractmethod
from types import SimpleNamespace


# Future functionality (as a non-participant):
#   - Accept/refuse actor connections
#   - Diconnect actors
#   - Request tick updates?
#   - Request any observation?
#   - Send messages?
#   - Request to receive every message?
class ControlSession(ABC):
    def __init__(self, trial, stub):
        self._trial = trial
        self._lifecycle_stub = stub

    def get_trial_id(self):
        return self._trial.id

    def get_actors(self):
        return [SimpleNamespace(actor_name=actor.name, actor_class_name=actor.actor_class)
                for actor in self._trial.actors]

    async def terminate_trial(self):
        req = orchestrator_api.TerminateTrialRequest()
        metadata = [("trial-id", self._trial.id)]
        await self._lifecycle_stub.TerminateTrial(
            request=req,
            metadata=metadata
        )


class _ServedControlSession(ControlSession):
    def __init__(self, trial, stub):
        super().__init__(trial, stub)

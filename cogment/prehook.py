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

from abc import ABC, abstractmethod
from cogment.errors import InvalidParamsError


class PrehookSession(ABC):
    """This represents the session for a prehook for a trial"""

    def __init__(self, params, trial):
        self._params = params
        self._trial = trial

        self.trial_config = params["trial_config"]
        self.trial_max_steps = params["max_steps"]
        self.trial_max_inactivity = params["max_inactivity"]

        self.environment_config = params["environment"]["config"]
        self.environment_endpoint = params["environment"]["endpoint"]

        self.actors = params["actors"]

    @abstractmethod
    def _recode(self):
        pass

    def get_trial_id(self):
        return self._trial.id

    def validate(self):
        unknowns = []
        for name in dir(self):
            if name and name[0] != "_":
                if (name != "trial_config" and name != "trial_max_steps" and name != "trial_max_inactivity" and
                        name != "environment_config" and name != "environment_endpoint" and name != "actors" and
                        name != "get_trial_id" and name != "validate"):
                    unknowns.append(name)
        if unknowns:
            raise InvalidParamsError(f"Unknown attributes for parameters: {unknowns}")

        self._recode()

    def __str__(self):
        result = f"PreHookSession: trial_config = {self.trial_config}"
        result += f", trial_max_steps = {self.trial_max_steps}"
        result += f", trial_max_inactivity = {self.trial_max_inactivity}"
        result += f", environment_config = {self.environment_config}"
        result += f", environment_endpoint = {self.environment_endpoint}"
        result += f", actors = {self.actors}"
        return result


class _ServedPrehookSession(PrehookSession):
    def __init__(self, params, trial):
        super().__init__(params, trial)

    def _recode(self):
        for act in self.actors:
            if "name" not in act or \
               "actor_class" not in act or \
               "endpoint" not in act or \
               "implementation" not in act or \
               "config" not in act:
                raise InvalidParamsError(f"incomplete actor: {act}")

        self._params["actors"] = self.actors

        self._params["trial_config"] = self.trial_config
        self._params["max_steps"] = self.trial_max_steps
        self._params["max_inactivity"] = self.trial_max_inactivity

        self._params["environment"]["config"] = self.environment_config
        self._params["environment"]["endpoint"] = self.environment_endpoint

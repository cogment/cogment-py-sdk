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

    def __init__(self, trial, user_id):
        self._trial = trial
        self._user_id = user_id

    def get_trial_id(self):
        return self._trial.id

    def get_user_id(self):
        return self._user_id

    def validate(self):
        attributes = {"trial_config", "trial_max_steps", "trial_max_inactivity", 
                      "environment_config", "environment_endpoint", "environment_name",
                      "actors", "get_trial_id", "get_user_id", "validate", "datalog_endpoint",
                      "datalog_type", "datalog_exclude"}
        for att in dir(self):
            if att and att[0] != "_" and att not in attributes:
                raise InvalidParamsError(f"Unknown attribute [{att}] for parameters")
        for att in attributes:
            if att not in dir(self):
                raise InvalidParamsError(f"Missing attribute [{att}] for parameters")

        actor_attributes = {"name", "actor_class", "endpoint", "implementation", "config"}
        for actor in self.actors:
            for att in actor_attributes:
                if att not in actor:
                    raise InvalidParamsError(f"Incomplete actor for parameters. Missing attribute [{att}]")
            for att in actor:
                if att not in actor_attributes:
                    raise InvalidParamsError(f"Unknown actor attribute [{att}] for parameters")

    def __str__(self):
        result = f"PreHookSession: trial_config = {self.trial_config}"
        result += f", trial_max_steps = {self.trial_max_steps}"
        result += f", trial_max_inactivity = {self.trial_max_inactivity}"
        result += f", environment_config = {self.environment_config}"
        result += f", environment_endpoint = {self.environment_endpoint}"
        result += f", environment_name = {self.environment_name}"
        result += f", actors = {self.actors}"
        return result


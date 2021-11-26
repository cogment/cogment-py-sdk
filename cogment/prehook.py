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

from cogment.errors import CogmentError


class PrehookSession():
    """Class representing the session of a pre-trial hook for a trial."""

    def __init__(self, trial, user_id):
        self._trial = trial
        self._user_id = user_id
        self._data_attributes = {"trial_config", "trial_max_steps", "trial_max_inactivity",
                      "datalog_endpoint", "datalog_exclude", "environment_implementation",
                      "environment_endpoint", "environment_name", "environment_config", "actors"}
        self._method_attributes = {"get_trial_id", "get_user_id", "validate"}
        self._attributes = self._data_attributes.union(self._method_attributes)
        self._actor_attributes = {"name", "actor_class", "endpoint", "implementation", "config"}

    def __str__(self):
        result = "PreHookSession:"
        for att in self._data_attributes :
            if hasattr(self, att):
                result += f", {att} = {getattr(self, att)}"

        return result

    def get_trial_id(self):
        return self._trial.id

    def get_user_id(self):
        return self._user_id

    def validate(self):
        for att in dir(self):
            if att and att[0] != "_" and att not in self._attributes:
                raise CogmentError(f"Unknown attribute [{att}] for parameters")
        for att in self._attributes:
            if att not in dir(self):
                raise CogmentError(f"Missing attribute [{att}] for parameters")

        for actor in self.actors:
            for att in self._actor_attributes:
                if att not in actor:
                    raise CogmentError(f"Incomplete actor for parameters. Missing attribute [{att}]")
            for att in actor:
                if att not in self._actor_attributes:
                    raise CogmentError(f"Unknown actor attribute [{att}] for parameters")

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

from types import SimpleNamespace
from abc import ABC


class Session(ABC):
    def __init__(self, trial):
        self._trial = trial

    def get_trial_id(self):
        return self._trial.id

    def get_tick_id(self):
        return self._trial.tick_id

    def is_trial_over(self):
        return self._trial.over

    def get_active_actors(self):
        return [SimpleNamespace(actor_name=actor.name, actor_class=actor.actor_class)
                for actor in self._trial.actors]

    def add_feedback(self, value, confidence, to, tick_id=-1, user_data=None):
        self._trial.add_feedback(value, confidence, to, tick_id, user_data)

    def send_message(self, user_data, to, to_environment=False):
        self._trial.send_message(user_data, to, to_environment)

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

from abc import ABC, abstractmethod


class Session(ABC):
    class ActiveActor:
        def __init__(self, actor_name, actor_class_name):
            self.actor_name = actor_name
            self.actor_class_name = actor_class_name

    def __init__(self, trial):
        self._trial = trial

        # Pre-compute since it will be used regularly
        self._active_actors = [self.ActiveActor(actor_name=actor.name, actor_class_name=actor.actor_class.id)
                             for actor in trial.actors]

    def get_trial_id(self):
        assert self._trial is not None
        return self._trial.id

    def get_tick_id(self):
        assert self._trial is not None
        return self._trial.tick_id

    def is_trial_over(self):
        assert self._trial is not None
        return self._trial.over

    def get_active_actors(self):
        assert self._trial is not None
        return self._active_actors

    @abstractmethod
    def add_reward(self, value, confidence, to, tick_id=-1, user_data=None):
        pass

    @abstractmethod
    def send_message(self, user_data, to, to_environment=False):
        pass

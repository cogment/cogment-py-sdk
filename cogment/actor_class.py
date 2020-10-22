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

class ActorClass:
    def __init__(self, id, config_type, action_space, observation_space,
                 observation_delta, observation_delta_apply_fn, feedback_space):
        self.id = id
        self.config_type = config_type
        self.action_space = action_space
        self.observation_space = observation_space
        self.observation_delta = observation_delta
        self.observation_delta_apply_fn = observation_delta_apply_fn
        self.feedback_space = feedback_space


class ActorClassList:
    def __init__(self, *args):
        self._actor_classes_list = list(args)

        for a_c in args:
            setattr(self, a_c.id, a_c)

    def __iter__(self):
        return iter(self._actor_classes_list)

    def get_actor_counts(self, trial_params):
        result = [0] * len(self._actor_classes_list)

        index_map = {}
        for index, actor_class in enumerate(self._actor_classes_list):
            index_map[actor_class.id] = index

        for actor in trial_params.actors:
            result[index_map[actor.actor_class]] += 1

        return result

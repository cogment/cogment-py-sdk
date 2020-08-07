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


class Trial:
    def __init__(self, id_, cog_project, trial_config):
        self.id_ = id_
        self.over = False

        self.actors = []

    def _add_actor(self, actor_class, actor_name):
        actor = Actor(actor_class, actor_name)
        self.actors.append(actor)


# A trial, from the perspective of the lifetime manager
class TrialLifecycle(Trial):
    def __init__(self, id_, cog_project, trial_config, actor_class_idx, actor_names):
        super().__init__(id_, cog_project, trial_config)

        assert len(actor_class_idx) == len(actor_names)
        for i, name in enumerate(actor_names):
            actor_class = cog_project.actor_classes.get_class_by_index(
                actor_class_idx[i]
            )
            self._add_actor(actor_class, name)

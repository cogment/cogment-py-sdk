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

from cogment.actor import Actor
from cogment.environment import Environment
from cogment.api.common_pb2 import Feedback, Message


class Trial:
    def __init__(self, id_, cog_project, trial_config):
        self.id_ = id_
        self.over = False
        self.cog_project = cog_project
        self.actors = []
        self.tick_id = 0

        self._actions = None  # Managed externally
        self._actions_by_actor_id = None  # Managed externally

        self.__actor_by_name = {}

    def _add_environment(self):
        self.environment = Environment()

    def get_environment(self):
        return self.environment

    def _add_actors(self, actors_in_trial):
        for actor_in_trial in actors_in_trial:
            # TODO, handle what happens when the class is not found.
            actor_class = self.cog_project.actor_classes[actor_in_trial.actor_class]
            actor = Actor(actor_class, actor_in_trial.name)
            self.actors.append(actor)

    def _add_actor_counts(self):
        class_list = self.cog_project.actor_classes._actor_classes_list
        self.actor_counts = [0] * len(class_list)
        for class_index, class_member in enumerate(class_list):
            for actor in self.actors:
                if class_member.id_ == actor.actor_class.id_:
                    self.actor_counts[class_index] += 1

    def get_actors(self, pattern):
        if isinstance(pattern, list):
            pattern_list = pattern
        else:
            pattern_list = [pattern]
        matched_actors = []
        for actor_index, actor in enumerate(self.actors):
            for single_pattern in pattern_list:
                if single_pattern == "*" or single_pattern == "*.*":
                    matched_actors.append(actor)
                    break
                elif isinstance(single_pattern, int):
                    if actor_index == single_pattern:
                        matched_actors.append(actor)
                        break
                elif isinstance(single_pattern, str):
                    if "." not in single_pattern:
                        if actor.name == single_pattern:
                            matched_actors.append(actor)
                            break
                    else:
                        [class_name, actor_name] = single_pattern.split(".")
                        if actor_name == actor.name:
                            matched_actors.append(actor)
                            break
                        elif actor_name == "*":
                            if actor.actor_class.id_ == class_name:
                                matched_actors.append(actor)
                                break

        return matched_actors

    def add_feedback(self, to, value, confidence):
        for d in self.get_actors(pattern=to):
            d.add_feedback(value=value, confidence=confidence)

    def _gather_all_feedback(self):
        for actor_index, actor in enumerate(self.actors):
            a_fb = actor._feedback
            actor._feedback = []

            for fb in a_fb:
                re = Feedback(
                    actor_id=actor_index, tick_id=fb[0], value=fb[1], confidence=fb[2]
                )
                if fb[3] is not None:
                    re.content = fb[3].SerializeToString()

                yield re

    def send_message(self, user_data, to, environment=False):
        if environment:
            self.environment.send_message(user_data=user_data)
        for d in self.get_actors(pattern=to):
            d.send_message(user_data=user_data)

    def _gather_all_messages(self, source_id):
        for actor_index, actor in enumerate(self.actors):
            a_msg = actor._message
            actor._message = []

            for msg in a_msg:
                re = Message(sender_id=source_id, receiver_id=actor_index)
                if msg is not None:
                    re.payload.Pack(msg)
                yield re

        e_msg = self.environment._message
        self.environment._message = []
        for msg in e_msg:
            re = Message(sender_id=source_id, receiver_id=-1)

            if msg is not None:
                re.payload.Pack(msg)
            yield re


# A trial, from the perspective of the lifetime manager
class TrialLifecycle(Trial):

    # trial config added for now
    def __init__(self, id_, trial_config, actors_in_trial, conn):
        super().__init__(id_, conn.cog_project, trial_config)
        self._add_actors(actors_in_trial)
        self._conn = conn

    async def terminate(self):
        await self._conn.terminate(trial_id=self.id_)

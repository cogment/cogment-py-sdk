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
from cogment.environment import Env
from cogment.api.common_pb2 import Feedback, Message


class Trial:
    def __init__(self, id_, cog_project, trial_config):
        self.id_ = id_
        self.over = False
        self.cog_project = cog_project
        self.actors = []
        self.tick_id = 0

        self.__actor_by_name = {}

    def _add_env(self):
        self.env = Env()

    def _add_actors(self, actors_in_trial):

        for actor in actors_in_trial:
            actor_class = self.cog_project.actor_classes[actor.actor_class]
            actor = Actor(actor_class, actor.name)
            self.actors.append(actor)

    def _add_actor_counts(self):
        class_list = self.cog_project.actor_classes._actor_classes_list
        self.actor_counts = [0] * len(class_list)
        for class_index, class_member in enumerate(class_list):
            for actor in self.actors:
                if class_member.id_ == actor.actor_class.id_:
                    self.actor_counts[class_index] += 1

    def get_receivers(self, pattern):
        if isinstance(pattern, int) or isinstance(pattern, str):
            pattern_list = [pattern]
        elif isinstance(pattern, list):
            pattern_list = pattern
        receiver_list = []
        all_receivers = self.actors + [self.env]
        for target in pattern_list:
            for receiver_index, receiver in enumerate(all_receivers, -1):
                if target == "*" or target == "*.*":
                    receiver_list.append(receiver)
                elif isinstance(target, int):
                    if receiver_index == target:
                        receiver_list.append(receiver)
                elif isinstance(target, str):
                    if "." not in target:
                        if receiver.name == target:
                            receiver_list.append(receiver)
                    else:
                        class_name = target.split(".")
                        if class_name[1] == receiver.name:
                            receiver_list.append(receiver)
                        elif class_name[1] == "*":
                            if receiver.actor_class.id_ == class_name[0]:
                                receiver_list.append(actor)

        return receiver_list

    def add_feedback(self, to, value, confidence):
        for d in self.get_receivers(pattern=to):
            d.add_feedback(value=value, confidence=confidence)

    def _gather_all_feedback(self):
        for actor_index, actor in enumerate(self.actors):
            a_fb = actor._feedback
            actor._feedback = []

            for fb in a_fb:
                re = Feedback(
                    actor_id=actor_index,
                    tick_id=fb[0],
                    value=fb[1],
                    confidence=fb[2]
                )
                if fb[3] is not None:
                    re.content = fb[3].SerializeToString()

                yield re

    def send_message(self, to, user_data):
        for d in self.get_receivers(pattern=to):
            d.send_message(user_data=user_data)

    def _gather_all_messages(self, source_id):
        for actor_index, actor in enumerate(self.actors):
            a_msg = actor._message
            actor._message = []

            for msg in a_msg:
                re = Message(
                    sender_id=source_id,
                    receiver_id=actor_index
                )
                if msg is not None:
                    re.payload.Pack(msg)
                yield re

        e_msg = self.env._message
        self.env._message = []
        for msg in e_msg:
            re = Message(
                sender_id=source_id,
                receiver_id=-1
            )

            if msg is not None:
                re.payload.Pack(msg)
            yield re


# A trial, from the perspective of the lifetime manager
class TrialLifecycle(Trial):
    def __init__(self, id_, cog_project, trial_config, actor_class_idx, actor_names):
        super().__init__(id_, cog_project, trial_config)
        self._add_actors(actor_class_idx, actor_names)

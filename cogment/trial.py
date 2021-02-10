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

from collections import deque
from typing import List

import cogment.api.common_pb2 as common_api
from cogment.environment import ENVIRONMENT_ACTOR_NAME
from cogment.errors import Error


class Trial:
    class Environment:
        def __init__(self):
            self.name = ENVIRONMENT_ACTOR_NAME
            self._messages = deque()

        def add_prepared_message(self, payload):
            self._messages.append(payload)

        def get_prepared_messages(self, sender_name):
            while len(self._messages) > 0:
                payload = self._messages.popleft()
                message = common_api.Message(tick_id=-1, sender_name=sender_name, receiver_name=self.name)
                if payload is not None:
                    message.payload.Pack(payload)
                yield message

    class Actor(Environment):
        def __init__(self, name, actor_class):
            super().__init__()
            self.name = name
            self.actor_class = actor_class
            self._reward_data = deque()

        def add_prepared_reward_data(self, tick_id, value, confidence, user_data):
            self._reward_data.append((tick_id, value, confidence, user_data))

        def get_prepared_rewards(self):
            while len(self._reward_data) > 0:
                (tick_id, reward_value, confidence, user_data) = self._reward_data.popleft()
                source = common_api.RewardSource(
                    # sender_name is not needed for sending rewards
                    value=reward_value,
                    confidence=confidence
                )
                if user_data is not None:
                    source.user_data.Pack(user_data)

                reward = common_api.Reward(
                    value=reward_value,  # This will be overwritten by orchestrator before delivery
                    receiver_name=self.name,
                    tick_id=tick_id,
                )
                reward.sources.append(source)
                yield reward

    def __init__(self, id, actors_in_trial, cog_settings):
        self.id = id
        self.over = False
        self.cog_settings = cog_settings
        self.tick_id = -1
        self.environment = self.Environment()

        self._actions = None  # Managed externally
        self._actions_by_actor_id = None  # Managed externally

        self.__actor_by_name = {}

        self.actors = []
        self.actor_counts = []
        self._add_actors(actors_in_trial)
        self._add_actor_counts()

    def _add_actors(self, actors_in_trial):
        for actor_in_trial in actors_in_trial:
            if actor_in_trial.actor_class not in self.cog_settings.actor_classes:
                raise Error(f"class '{actor_in_trial.actor_class}' of actor '{actor_in_trial.name}' can not be found.")
            actor_class = self.cog_settings.actor_classes[actor_in_trial.actor_class]
            actor = self.Actor(
                name=actor_in_trial.name,
                actor_class=actor_class
            )
            self.actors.append(actor)

    def _add_actor_counts(self):
        class_list = self.cog_settings.actor_classes._actor_classes_list
        self.actor_counts = [0] * len(class_list)
        for class_index, class_member in enumerate(class_list):
            for actor in self.actors:
                if class_member.id == actor.actor_class.id:
                    self.actor_counts[class_index] += 1

    def get_actors(self, pattern_list: List[str]):
        if not isinstance(pattern_list, list):
            raise TypeError(f"The pattern_list must be a list: {type(pattern_list)}")
        matched_actors = []
        for actor in self.actors:
            for pattern in pattern_list:
                if not isinstance(pattern, str):
                    raise TypeError(f"The pattern must be a string: {type(pattern)}")
                if pattern == "*":
                    matched_actors.append(actor)
                    break
                else:
                    if "." not in pattern:
                        if actor.name == pattern:
                            matched_actors.append(actor)
                            break
                    else:
                        [class_name, actor_name] = pattern.split(".")
                        if actor_name == actor.name:
                            matched_actors.append(actor)
                            break
                        elif actor_name == "*":
                            if actor.actor_class.id == class_name:
                                matched_actors.append(actor)
                                break

        return matched_actors

    # TODO: Add source actor to set in reward
    def add_reward(self, value, confidence, to, tick_id, user_data):
        for dest_actor in self.get_actors(pattern_list=to):
            dest_actor.add_prepared_reward_data(
                tick_id=tick_id,
                value=value,
                confidence=confidence,
                user_data=user_data
            )

    def _gather_all_rewards(self):
        for actor in self.actors:
            for reward in actor.get_prepared_rewards():
                yield reward

    # We default `to` so users can provide a `to_environment=True` without a `to` parameter
    def send_message(self, user_data, to=[], to_environment=False):
        if to_environment:
            self.environment.add_prepared_message(payload=user_data)
        for actor in self.get_actors(pattern_list=to):
            actor.add_prepared_message(payload=user_data)

    def _gather_all_messages(self, source_name):
        for actor in self.actors:
            for message in actor.get_prepared_messages(source_name):
                yield message

        for message in self.environment.get_prepared_messages(source_name):
            yield message

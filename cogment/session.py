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
from enum import Enum
import logging


class RecvObservation:
    def __init__(self, obs, snapshot):
        self.tick_id = obs.tick_id
        self.timestamp = obs.timestamp
        self.snapshot = snapshot

    def __str__(self):
        result = f"RecvObservation: tick_id = {self.tick_id}, timestamp = {self.timestamp}"
        result += f", snapshot = {self.snapshot}"
        return result


class RecvAction:
    def __init__(self, actor_index, action):
        self.actor_index = actor_index
        self.action = action

    def __str__(self):
        result = f"RecvAction: actor index = {self.actor_index}"
        result += f", action = {self.action}"
        return result


class RecvReward:
    def __init__(self, reward):
        self.tick_id = reward.tick_id
        self.value = reward.value
        self._sources = reward.sources

    def get_nb_sources(self):
        return len(self._sources)

    def all_sources(self):
        assert self._sources
        for src in self._sources:
            yield (src.value, src.confidence, src.sender_name, src.user_data)

    def __str__(self):
        result = f"RecvReward: tick_id = {self.tick_id}, value = {self.value}"
        result += f", sources = {self._sources}"
        return result


class RecvMessage:
    def __init__(self, message):
        self.tick_id = message.tick_id
        self.sender_name = message.sender_name
        self.payload = message.payload

    def __str__(self):
        result = f"RecvMessage: tick_id = {self.tick_id}, sender_name = {self.sender_name}"
        result += f", payload = {self.payload}"
        return result


class EventType(Enum):
    NONE = 0
    ACTIVE = 1
    ENDING = 2
    FINAL = 3


class RecvEvent:
    def __init__(self, etype):
        self.type = etype
        self.observation = None
        self.actions = []
        self.rewards = []
        self.messages = []

    def __str__(self):
        result = f"RecvEvent: type = {self.type}"
        if self.observation:
            result += f", {{{self.observation}}}"
        for act in self.actions:
            result += f", {{{act}}}"
        for rew in self.rewards:
            result += f", {{{rew}}}"
        for msg in self.messages:
            result += f", {{{msg}}}"
        return result


class Session(ABC):
    class ActiveActor:
        def __init__(self, actor_name, actor_class_name):
            self.actor_name = actor_name
            self.actor_class_name = actor_class_name

    def __init__(self, trial):
        self._trial = trial

        # Pre-compute since it will be used regularly
        self._active_actors = [self.ActiveActor(actor_name=actor.name, actor_class_name=actor.actor_class.name)
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

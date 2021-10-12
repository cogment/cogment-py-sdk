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

import time
from abc import abstractmethod
from typing import Any
from cogment.session import Session
from cogment.errors import CogmentError

import cogment.api.common_pb2 as common_api


class ActorClass:
    def __init__(
        self,
        name,
        config_type,
        action_space,
        observation_space,
    ):
        self.name = name
        self.config_type = config_type
        self.action_space = action_space
        self.observation_space = observation_space

    def __str__(self):
        result = f"ActorClass: name = {self.name}, config_type = {type(self.config_type)}"
        result += f", action_space = {type(self.action_space)}, observation_space = {type(self.observation_space)}"
        return result


class ActorClassList:
    def __init__(self, *args):
        self._actor_classes_list = list(args)

        for a_c in args:
            setattr(self, a_c.name, a_c)

    def __iter__(self):
        return iter(self._actor_classes_list)

    def __contains__(self, key):
        return hasattr(self, key)

    def __getitem__(self, key):
        return getattr(self, key)

    def get_class_by_index(self, index):
        return self._actor_classes_list[index]

    def __str__(self):
        result = f"ActorClassList:"
        for ac in self._actor_classes_list:
            result += f" {ac.name} = {{{ac}}},"
        return result


class ActorSession(Session):
    """This represents an actor being performed locally."""

    def __init__(self, impl, actor_class, trial, name, impl_name, config):
        super().__init__(trial, name, impl, impl_name)
        self.class_name = actor_class.name
        self.config = config

        self._actor_class = actor_class

    def __str__(self):
        result = super().__str__()
        result += f" --- ActorSession: class_name = {self.class_name}, config = {self.config}"
        return result

    def start(self, auto_done_sending=True):
        self._start(auto_done_sending)

    def do_action(self, action):
        action_req = common_api.Action()
        action_req.timestamp = int(time.time() * 1000000000)
        action_req.tick_id = -1
        if action is not None:
            action_req.content = action.SerializeToString()

        self._post_data(action_req)

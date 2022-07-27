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

import cogment.api.common_pb2 as common_api

from cogment.session import Session
from cogment.errors import CogmentError
from cogment.utils import logger

import time


class ActorClass:
    """Class containing the details of an actor class defined in a config file."""

    def __init__(self, name, config_type, action_space, observation_space):
        self.name = name
        self.config_type = config_type
        self.action_space = action_space
        self.observation_space = observation_space

    def __str__(self):
        result = f"ActorClass: name = {self.name}, config_type = {type(self.config_type)}"
        result += f", action_space = {type(self.action_space)}, observation_space = {type(self.observation_space)}"
        return result


class ActorClassList:
    """Class containing the list of actor classes defined in a config file."""

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
            result += f" {ac.name} = {ac},"
        return result

    def get(self, key, default=None):  # Similar to dict.get()
        return getattr(self, key, default)


class ActorSession(Session):
    """Derived class representing the session of an actor for a trial."""

    def __init__(self, impl, actor_class, trial, name, impl_name, env_name, config):
        super().__init__(trial, name, impl, impl_name, config)
        self.class_name = actor_class.name
        self.env_name = env_name
        self._actor_class = actor_class

    def __str__(self):
        result = super().__str__()
        result += f" --- ActorSession: class_name = {self.class_name}, config = {self.config}"
        return result

    def get_active_actors(self):
        # Controller.get_actors can be used.
        # Or provide actors details in the config, or the observations.
        raise CogmentError(f"This function is deprecated for actors")

    def start(self, auto_done_sending=True):
        self._start(auto_done_sending)

    def do_action(self, action):
        action_req = common_api.Action()
        action_req.timestamp = int(time.time() * 1e9)
        action_req.tick_id = self._last_tick_delivered
        if action is not None:
            action_req.content = action.SerializeToString()

        self._post_outgoing_data(action_req)

    def send_message(self, payload, to, to_environment=None):
        if to_environment is not None:
            logger.deprecated("Parameter 'to_environment' is deprecated for 'send_message' method. "
                              "Use 'self.env_name' as environment name in the 'to' parameter.")
            if to_environment:
                self._send_message(payload, to + [self.env_name])
                return
        self._send_message(payload, to)

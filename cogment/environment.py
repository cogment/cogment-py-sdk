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

import asyncio
import importlib
import logging
from cogment.session import Session
from abc import ABC, abstractmethod

ENVIRONMENT_ACTOR_NAME = "env"


class Environment:
    def __init__(self):
        self.env_id = -1
        self.name = ENVIRONMENT_ACTOR_NAME

        self._message = []

    def send_message(self, user_data):
        self._message.append((user_data))


class EnvironmentSession(Session):
    """This represents the environment being performed locally."""

    def __init__(self, impl, trial, impl_name, config):
        super().__init__(trial)
        self.impl_name = impl_name
        self.config = config

        # Callbacks
        self.on_actions = None
        self.on_message = None
        self.on_end_request = None

        self._end_trial = False
        self._ignore_incoming_actions = False

        self.__impl = impl
        self.__started = False
        self.__actions_future = None

    @abstractmethod
    def _consume_obs(self, observations, final):
        pass

    def start(self, observations):
        assert not self.__started
        self.__started = True

        self._consume_obs(observations, False)

    async def gather_actions(self):
        assert self.__started
        assert self.on_actions is None

        self.__actions_future = asyncio.get_running_loop().create_future()
        return await self.__actions_future

    def produce_observations(self, observations):
        assert self.__started
        self._consume_obs(observations, False)

    def end(self, observations):
        if not self._end_trial:
            self._end_trial = True
            self._consume_obs(observations, True)

    async def _end_request(self, actions):
        rep = None
        if not self._end_trial:
            self._end_trial = True
            if self.on_end_request is not None:
                rep = await self.on_end_request(actions)

        return rep

    def _new_action(self, actions):
        if self._end_trial:
            return

        if self.on_actions is not None:
            self.on_actions(actions)
            self.__actions_future = None
        elif self.__actions_future:
            self.__actions_future.set_result(actions)
            self.__actions_future = None
        else:
            logging.warning("The environment received actions that it was unable to handle.")

    def _new_message(self, message):
        if self.on_message is not None:
            class_type = message.payload.type_url.split(".")
            user_data = getattr(
                importlib.import_module(self._trial.cog_project.protolib), class_type[-1]
            )()
            message.payload.Unpack(user_data)
            self.on_message(message.sender_name, user_data)
        else:
            logging.info("A message arived but was not handled.")

    async def _run(self):
        await self.__impl(self)


class _ServedEnvironmentSession(EnvironmentSession):
    """An environment session that is served from an environment service."""

    def __init__(self, impl, trial, impl_name, config):
        super().__init__(impl, trial, impl_name, config)
        self._obs_queue = asyncio.Queue()

    # maybe needs to be consume observation
    def _consume_obs(self, observations, final):
        self._obs_queue.put_nowait((observations, final))

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

        self._ended = False
        self._obs_queue = asyncio.Queue()
        self._task = None  # Task used to call _run()

        self.__impl = impl
        self.__started = False
        self.__event_queue = None
        self.__final_obs_future = None

    @abstractmethod
    async def _retrieve_obs(self):
        pass

    def start(self, observations):
        assert not self.__started
        assert not self._ended

        self.__event_queue = asyncio.Queue()
        self.__started = True

        self._obs_queue.put_nowait(observations)

    async def event_loop(self):
        assert self.__started
        assert not self._ended

        loop_active = True
        while loop_active:
            event = await self.__event_queue.get()
            keep_looping = yield event
            self.__event_queue.task_done()
            loop_active = keep_looping is None or bool(keep_looping)

    def produce_observations(self, observations):
        assert self.__started
        self._obs_queue.put_nowait((observations, False))

    def end(self, observations):
        if self.__final_obs_future is not None:
            self.__final_obs_future.set_result(observations)
        elif not self._ended:
            self._ended = True
            self._obs_queue.put_nowait((observations, True))

    async def _end_request(self, actions):
        if self._ended:
            return None
        self._ended = True
        if not self.__started:
            return None

        # self.__event_queue.join()

        result = None
        if self.__event_queue:
            self.__final_obs_future = asyncio.get_running_loop().create_future()

            event = {"final_actions" : actions}
            self.__event_queue.put_nowait(event)

            result = await self.__final_obs_future()
            self.__final_obs_future = None
        else:
            logging.warning("The environment received an end request that it was unable to handle.")

        return result

    def _new_action(self, actions):
        if not self.__started or self._ended:
            return

        if self.__event_queue:
            event = {"actions" : actions}
            self.__event_queue.put_nowait(event)
        else:
            logging.warning("The environment received actions that it was unable to handle.")

    def _new_message(self, message):
        if not self.__started or self._ended:
            return

        if self.__event_queue:
            event = {"message" : (message.sender_name(), message.payload())}
            self.__event_queue.put_nowait(event)
        else:
            logging.warning("The environment received a message that it was unable to handle.")

    async def _run(self):
        await self.__impl(self)


class _ServedEnvironmentSession(EnvironmentSession):
    """An environment session that is served from an environment service."""

    def __init__(self, impl, trial, impl_name, config):
        super().__init__(impl, trial, impl_name, config)

    async def _retrieve_obs(self):
        obs = (None, False)
        if self._obs_queue is not None:
            obs = await self._obs_queue.get()
            self._obs_queue.task_done()

        return obs

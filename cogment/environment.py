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

import asyncio
import importlib
import logging
from cogment.session import Session, EventType
from abc import ABC

ENVIRONMENT_ACTOR_NAME = "env"


class EnvironmentSession(Session):
    """This represents the environment being performed locally."""

    def __init__(self, impl, trial, impl_name, config):
        super().__init__(trial, ENVIRONMENT_ACTOR_NAME, impl, impl_name)
        self.config = config
        self._obs_queue = asyncio.Queue()
        self.__final_obs_future = None

    def start(self, observations):
        if self._start():
            self._obs_queue.put_nowait((observations, False))

    def produce_observations(self, observations):
        if self._event_queue is None:
            logging.warning("Cannot send observations until the environment is started.")
            return

        if self.__final_obs_future is not None:
            self.__final_obs_future.set_result(observations)
        elif not self.is_trial_over():
            self._obs_queue.put_nowait((observations, False))
        else:
            logging.warning("Cannot send observation because the trial has ended.")

    def end(self, observations):
        if self.__final_obs_future is not None:
            self.__final_obs_future.set_result(observations)
        elif not self.is_trial_over():
            self._obs_queue.put_nowait((observations, True))
        else:
            logging.warning("Cannot end the environment because the trial has already ended.")

    async def _retrieve_obs(self):
        obs = await self._obs_queue.get()
        self._obs_queue.task_done()
        return obs

    async def _end_request(self, event):
        logging.debug("Environment received an end request")

        if self.is_trial_over():
            return None
        if self._event_queue is None:
            logging.warning("The environment received an end request before it was started.")
            return None

        self.__final_obs_future = asyncio.get_running_loop().create_future()

        await self._event_queue.put(event)

        result = await self.__final_obs_future
        self.__final_obs_future = None

        return result

    def __str__(self):
        result = super().__str__()
        result += f" --- EnvironmentSession: config = {self.config}"
        return result


class _ServedEnvironmentSession(EnvironmentSession):
    """An environment session that is served from an environment service."""

    def __init__(self, impl, trial, impl_name, config):
        super().__init__(impl, trial, impl_name, config)

    def add_reward(self, value, confidence, to, tick_id=-1, user_data=None):
        self._trial.add_reward(value, confidence, to, tick_id, user_data)

    def send_message(self, payload, to, to_environment=False):
        self._trial.send_message(payload, to, to_environment)

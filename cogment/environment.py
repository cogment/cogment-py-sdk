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
import traceback
from cogment.session import Session
from abc import ABC

ENVIRONMENT_ACTOR_NAME = "env"

_ACTIONS = "actions"
_FINAL_ACTIONS = "final_actions"
_MESSAGE = "message"


class EnvironmentSession(Session):
    """This represents the environment being performed locally."""

    def __init__(self, impl, trial, impl_name, config):
        super().__init__(trial)
        self.impl_name = impl_name
        self.config = config

        self._ended = False
        self._obs_queue = asyncio.Queue()
        self._last_event_received = False
        self._task = None  # Task used to call _run()

        self.__impl = impl
        self.__started = False
        self.__event_queue = None
        self.__final_obs_future = None

    def start(self, observations):
        assert not self.__started
        assert not self._ended

        self.__event_queue = asyncio.Queue()
        self.__started = True

        self._obs_queue.put_nowait((observations, False))

    async def event_loop(self):
        assert self.__started
        assert not self._ended

        loop_active = not self._last_event_received
        while loop_active:
            try:
                event = await self.__event_queue.get()

            except asyncio.CancelledError:
                logging.debug("Coroutine cancelled while waiting for an event")
                break

            self._last_event_received = _FINAL_ACTIONS in event
            keep_looping = yield event
            self.__event_queue.task_done()
            loop_active = ((keep_looping is None or bool(keep_looping)) and
                            not self._last_event_received and
                            not self._ended)

            if not loop_active:
                if self._last_event_received:
                    logging.debug(f"Last event received, exiting environment event loop")
                elif self._ended:
                    logging.debug(f"Last observation sent, exiting environment event loop")
                else:
                    logging.debug(f"End of event loop for environment requested by user")

        logging.debug(f"Exiting environment event loop generator")

    def produce_observations(self, observations):
        assert self.__started
        self._obs_queue.put_nowait((observations, False))

    def end(self, observations):
        if self.__final_obs_future is not None:
            self.__final_obs_future.set_result(observations)
        elif not self._ended:
            self._ended = True
            self._obs_queue.put_nowait((observations, True))

    async def _retrieve_obs(self):
        obs = await self._obs_queue.get()
        self._obs_queue.task_done()
        return obs

    async def _end_request(self, actions):
        logging.debug("Environment received an end request")

        if self._ended:
            return None
        self._ended = True
        if not self.__started:
            return None

        result = None
        if self.__event_queue:
            self.__final_obs_future = asyncio.get_running_loop().create_future()

            event = {_FINAL_ACTIONS : actions}
            await self.__event_queue.put(event)

            result = await self.__final_obs_future
            self.__final_obs_future = None
        else:
            logging.warning("The environment received an end request that it was unable to handle.")

        return result

    def _new_action(self, actions):
        if not self.__started or self._ended:
            return

        if self.__event_queue:
            event = {_ACTIONS : actions}
            self.__event_queue.put_nowait(event)
        else:
            logging.warning("The environment received actions that it was unable to handle.")

    def _new_message(self, message):
        logging.debug("Environment received a message")

        if not self.__started or self._ended:
            return

        if self.__event_queue:
            event = {_MESSAGE : (message.sender_name(), message.payload())}
            self.__event_queue.put_nowait(event)
        else:
            logging.warning("The environment received a message that it was unable to handle.")

    async def _run(self):
        try:
            await self.__impl(self)

        except asyncio.CancelledError:
            logging.debug("Environment implementation coroutine cancelled")

        except Exception:
            logging.error(f"An exception occured in user environment implementation:\n{traceback.format_exc()}")
            raise


class _ServedEnvironmentSession(EnvironmentSession):
    """An environment session that is served from an environment service."""

    def __init__(self, impl, trial, impl_name, config):
        super().__init__(impl, trial, impl_name, config)

    def add_reward(self, value, confidence, to, tick_id=-1, user_data=None):
        assert self._trial is not None
        self._trial.add_reward(value, confidence, to, tick_id, user_data)

    def send_message(self, user_data, to, to_environment=False):
        assert self._trial is not None
        self._trial.send_message(user_data, to, to_environment)

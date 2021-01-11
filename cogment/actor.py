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
from abc import ABC, abstractmethod
from cogment.session import Session


_OBSERVATION = "observation"
_FINAL_DATA = "final_data"
_MESSAGE = "message"
_REWARD = "reward"


class ActorClass:
    def __init__(
        self,
        id,
        config_type,
        action_space,
        observation_space,
        observation_delta,
        observation_delta_apply_fn,
        feedback_space,
    ):
        self.id = id
        self.config_type = config_type
        self.action_space = action_space
        self.observation_space = observation_space
        self.observation_delta = observation_delta
        self.observation_delta_apply_fn = observation_delta_apply_fn
        self.feedback_space = feedback_space


class ActorClassList:
    def __init__(self, *args):
        self._actor_classes_list = list(args)

        for a_c in args:
            setattr(self, a_c.id, a_c)

    def __iter__(self):
        return iter(self._actor_classes_list)

    def __contains__(self, key):
        return hasattr(self, key)

    def __getitem__(self, key):
        return getattr(self, key)

    def get_class_by_index(self, index):
        return self._actor_classes_list[index]


class Reward:
    def __init__(self):
        self.tick_id = -1
        self.value = 0
        self.confidence = 0

        self._feedbacks = None

    def _set_all(self, reward, tick_id):
        self.tick_id = tick_id
        self.value = reward.value
        self.confidence = reward.confidence
        self._set_feedbacks(reward.feedbacks)

    def _set_feedbacks(self, feedbacks):
        self._feedbacks = feedbacks
        if self.tick_id == -1 and self._feedbacks:
            self.tick_id = self._feedbacks[0].tick_id

    def all_user_data(self):
        assert self._feedbacks
        for fdbk in self._feedbacks:
            assert fdbk.tick_id == self.tick_id
            if fdbk.content:
                yield fdbk.content


class ActorSession(Session):
    """This represents an actor being performed locally."""

    def __init__(self, impl, actor_class, trial, name, impl_name, config):
        super().__init__(trial)
        self.class_name = actor_class.id
        self.name = name
        self.impl_name = impl_name
        self.config = config

        self._actor_class = actor_class
        self._ended = False
        self._action_queue = asyncio.Queue()
        self._task = None  # Task used to call _run()
        self._latest_observation = None
        self._last_event_received = False

        self.__impl = impl
        self.__started = False
        self.__event_queue = None
        self.__obs_future = None

    @abstractmethod
    async def _retrieve_action(self):
        pass

    def start(self):
        assert not self.__started
        assert not self._ended

        self.__event_queue = asyncio.Queue()
        self.__started = True

    async def event_loop(self):
        assert self.__started
        assert not self._ended

        loop_active = not self._last_event_received
        while loop_active:
            event = await self.__event_queue.get()
            self._last_event_received = _FINAL_DATA in event
            keep_looping = yield event
            self.__event_queue.task_done()
            loop_active = (keep_looping is None or bool(keep_looping)) and not self._last_event_received

    def do_action(self, action):
        assert self.__started
        self._action_queue.put_nowait(action)

    async def _end(self, package):
        logging.debug(f"Actor [{self.name}] received final data")
        if not self._ended:
            self._ended = True

        if self.__event_queue:
            std_messages = []
            for msg in package.messages:
                std_messages.append((msg.sender_name(), msg.payload()))
            package.messages = std_messages

            event = {_FINAL_DATA : package}
            await self.__event_queue.put(event)
        else:
            logging.warning(f"Actor [{self.name}] received final data that it was unable to handle.")

    def _new_observation(self, obs):
        logging.debug(f"Actor [{self.name}] received an observation")
        if not self.__started or self._ended:
            return

        if self.__event_queue:
            event = {_OBSERVATION : obs}
            self.__event_queue.put_nowait(event)
        else:
            logging.warning(f"Actor [{self.name}] received an observation that it was unable to handle.")

    def _new_reward(self, reward):
        logging.debug(f"Actor [{self.name}] received a reward")
        if not self.__started or self._ended:
            return

        if self.__event_queue:
            event = {_REWARD : reward}
            self.__event_queue.put_nowait(event)
        else:
            logging.warning(f"Actor [{self.name}] received a reward that it was unable to handle.")

    def _new_message(self, message):
        logging.debug(f"Actor [{self.name}] received a message")
        if not self.__started or self._ended:
            return

        if self.__event_queue:
            event = {_MESSAGE : (message.sender_name, message.payload)}
            self.__event_queue.put_nowait(event)
        else:
            logging.warning(f"Actor [{self.name}] received a message that it was unable to handle.")

    async def _run(self):
        try:
            await self.__impl(self)
        except Exception:
            logging.error(f"An exception occured in user agent implementation:\n{traceback.format_exc()}")
            raise


class _ServedActorSession(ActorSession):
    def __init__(self, impl, actor_class, trial, name, impl_name, config):
        super().__init__(impl, actor_class, trial, name, impl_name, config)

    async def _retrieve_action(self):
        action = await self._action_queue.get()
        self._action_queue.task_done()
        logging.debug(f"Agent actor [{self.name}] action has been retrieved")
        return action


class _ClientActorSession(ActorSession):
    def __init__(self, impl, actor_class, trial, name, impl_name, config):
        super().__init__(impl, actor_class, trial, name, impl_name, config)

    async def _retrieve_action(self):
        action = await self._action_queue.get()
        self._action_queue.task_done()
        logging.debug(f"Client actor [{self.name}] action has been retrieved")
        return action

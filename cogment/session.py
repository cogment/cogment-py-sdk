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

from abc import ABC, abstractmethod
from enum import Enum
import logging
import traceback
import asyncio


class ActorInfo:
    def __init__(self, name, class_name):
        self.actor_name = name
        self.actor_class_name = class_name

    def __str__(self):
        result = f"ActorInfo: actor name = {self.actor_name}, actor class name = {self.actor_class_name}"
        return result


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


class RecvRewardSource:
    def __init__(self, src):
        self.value = src.value
        self.confidence = src.confidence
        self.sender_name = src.sender_name
        self.user_data = src.user_data

    def __str__(self):
        result = f"RecvRewardSource: value = {self.value}, confidence = {self.confidence}"
        result += f", sender name = {self.sender_name}, user data = {self.user_data}"
        return result


class RecvReward:
    def __init__(self, reward):
        self.tick_id = reward.tick_id
        self.value = reward.value
        self._sources = reward.sources

    def get_nb_sources(self):
        return len(self._sources)

    def all_sources(self):
        if not self._sources:
            raise RuntimeError("Unexpected reward with no source")
        for src in self._sources:
            yield RecvRewardSource(src)

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
    def __init__(self, trial, name, impl, impl_name):
        self._trial = trial
        self.name = name
        self.impl_name = impl_name
        self._impl = impl
        self._event_queue = None  # Also used to know if we started
        self._last_event_delivered = False
        self._last_event_received = False
        self._task = None  # Task used to call _run()

        # Pre-compute since it will be used regularly
        self._active_actors = [ActorInfo(actor.name, actor.actor_class.name) for actor in trial.actors]

    def _start(self):
        if self._event_queue is not None:
            logging.warning(f"Cannot start [{self.name}] more than once. Data dropped.")
            return False
        if self._trial.over:
            logging.error(f"Cannot start [{self.name}] because the trial has ended.")
            return False

        self._event_queue = asyncio.Queue()
        return True

    async def _run(self):
        try:
            await self._impl(self)
            return True

        except asyncio.CancelledError as exc:
            logging.debug(f"[{self.name}] implementation coroutine cancelled: [{exc}]")
            return False

        except Exception:
            logging.error(f"An exception occured in user implementation of [{self.name}]:\n{traceback.format_exc()}")
            raise

    def _new_event(self, event):
        if self._event_queue is None:
            logging.warning(f"[{self.name}] received an event before session was started.")
            return
        if self._last_event_received:
            logging.debug(f"Event received after final event: [{event}]")
            return

        if event is not None and event.type == EventType.FINAL:
            self._last_event_received = True

        self._event_queue.put_nowait(event)

    async def event_loop(self):
        if self._event_queue is None:
            logging.warning(f"Event loop is not enabled until the [{self.name}] is started.")
            return
        if self._trial.over:
            logging.info(f"No more events for [{self.name}] because the trial has ended.")
            return

        loop_active = not self._last_event_delivered
        while loop_active:
            try:
                event = await self._event_queue.get()

            except asyncio.CancelledError as exc:
                logging.debug(f"[{self.name}] coroutine cancelled while waiting for an event: [{exc}]")
                break

            self._last_event_delivered = (event.type == EventType.FINAL)
            keep_looping = yield event
            self._event_queue.task_done()
            loop_active = (keep_looping is None or bool(keep_looping)) and not self._last_event_delivered
            if not loop_active:
                if self._last_event_delivered:
                    logging.debug(f"Last event delivered, exiting [{self.name}] event loop")
                else:
                    logging.debug(f"End of event loop for [{self.name}] requested by user")

        logging.debug(f"Exiting [{self.name}] event loop generator")

    def get_trial_id(self):
        return self._trial.id

    def get_tick_id(self):
        return self._trial.tick_id

    def is_trial_over(self):
        return self._trial.over

    def get_active_actors(self):
        return self._active_actors

    @abstractmethod
    def add_reward(self, value, confidence, to, tick_id=-1, user_data=None):
        pass

    @abstractmethod
    def send_message(self, payload, to, to_environment=False):
        pass

    def __str__(self):
        result = f"Session: name = {self.name}, impl_name = {self.impl_name}"
        return result

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
from abc import ABC, abstractmethod
from cogment.session import Session


class Actor:
    def __init__(self, actor_class, name):
        self.actor_class = actor_class
        self.name = name

        self._feedback = []
        self._message = []

    def add_feedback(self, value, confidence, tick_id, user_data):
        self._feedback.append((tick_id, value, confidence, user_data))

    def send_message(self, user_data):
        self._message.append(user_data)


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
        self.actor_class = actor_class
        self.name = name
        self.impl_name = impl_name
        self.config = config

        # Callbacks
        self.on_observation = None
        self.on_reward = None
        self.on_message = None
        self.on_trial_over = None

        self._latest_observation = None
        self.__impl = impl
        self.__started = False
        self.__obs_future = None
        self._task = None

    @abstractmethod
    async def _consume_action(self, action):
        pass

    def start(self):
        assert not self.__started
        self.__started = True

    async def _end(self, package):
        if self.on_trial_over is not None:
            self.on_trial_over(package)
        self.__obs_future = None

    async def get_observation(self):
        assert self.__started
        assert self.on_observation is None

        if self.is_trial_over():
            return None

        self.__obs_future = asyncio.get_running_loop().create_future()
        return await self.__obs_future

    async def get_all_observations(self):
        while not self.is_trial_over():
            obs = await self.get_observation()
            if obs is None:
                break
            action = yield obs
            if action:
                self.do_action(action)

    async def do_action(self, action):
        assert self.__started
        await self._consume_action(action)

    def _new_observation(self, obs):
        self._latest_observation = obs

        if self.on_observation is not None:
            self.on_observation(obs)
            self.__obs_future = None
        elif self.__obs_future is not None:
            self.__obs_future.set_result(obs)
            self.__obs_future = None
        elif self.__started:
            logging.warning("An observation was missed")

    def _new_reward(self, reward):
        if self.on_reward is not None:
            self.on_reward(reward)
        elif self.__started:
            logging.warning("A reward arived but was not handled.")

    def _new_message(self, message):
        if self.on_message is not None:
            class_type = message.payload.type_url.split(".")
            user_data = getattr(importlib.import_module(
                self._trial.cog_project.protolib), class_type[-1])()
            message.payload.Unpack(user_data)
            self.on_message(message.sender_name, user_data)
        elif self.__started:
            logging.info("A message arived but was not handled.")

    async def _run(self):
        await self.__impl(self)


class _ServedActorSession(ActorSession):
    def __init__(self, impl, actor_class, trial, name, impl_name, config):
        super().__init__(impl, actor_class, trial, name, impl_name, config)
        self._action_queue = asyncio.Queue()

    async def _consume_action(self, action):
        await self._action_queue.put(action)


class _ClientActorSession(ActorSession):
    def __init__(self, impl, actor_class, trial, name, impl_name, config):
        super().__init__(impl, actor_class, trial, name, impl_name, config)
        self._action_queue = asyncio.Queue()

    async def _consume_action(self, action):
        await self._action_queue.put(action)

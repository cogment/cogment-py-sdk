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
from abc import ABC
from cogment.session import Session, EventType
from cogment.environment import ENVIRONMENT_ACTOR_NAME

import cogment.api.orchestrator_pb2 as orchestrator_api
import cogment.api.common_pb2 as common_api


class ActorClass:
    def __init__(
        self,
        name,
        config_type,
        action_space,
        observation_space,
        observation_delta,
        observation_delta_apply_fn,
    ):
        self.name = name
        self.config_type = config_type
        self.action_space = action_space
        self.observation_space = observation_space
        self.observation_delta = observation_delta
        self.observation_delta_apply_fn = observation_delta_apply_fn

    def __str__(self):
        result = f"ActorClass: name = {self.name}, config_type = {type(self.config_type)}"
        result += f", action_space = {type(self.action_space)}, observation_space = {type(self.observation_space)}"
        result += f", observation_delta = {type(self.observation_delta)}"
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
        self._action_queue = asyncio.Queue()
        self._latest_observation = None

        self.__obs_future = None

    def start(self):
        self._start()

    def do_action(self, action):
        if self._event_queue is None:
            logging.warning(f"Cannot send action until actor [{self.name}] is started.")
            return
        self._action_queue.put_nowait(action)

    async def _retrieve_action(self):
        try:
            action = await self._action_queue.get()
            self._action_queue.task_done()
            return action

        except RuntimeError as exc:
            # Unfortunatelty asyncio returns a standard RuntimeError in this case
            if exc.args[0] != "Event loop is closed":
                raise
            else:
                logging.debug(f"Normal exception on retrieving action at close: [{exc}]")

        return None

    def __str__(self):
        result = super().__str__()
        result += f" --- ActorSession: class_name = {self.class_name}, config = {self.config}"
        return result


class _ServedActorSession(ActorSession):
    def __init__(self, impl, actor_class, trial, name, impl_name, config):
        super().__init__(impl, actor_class, trial, name, impl_name, config)

    def add_reward(self, value, confidence, to, tick_id=-1, user_data=None):
        self._trial.add_reward(value, confidence, to, tick_id, user_data)

    def send_message(self, payload, to, to_environment=False):
        self._trial.send_message(payload, to, to_environment)


class _ClientActorSession(ActorSession):
    def __init__(self, impl, actor_class, trial, name, impl_name, config, actor_stub):
        super().__init__(impl, actor_class, trial, name, impl_name, config)
        self._actor_sub = actor_stub

    def add_reward(self, value, confidence, to, tick_id=-1, user_data=None):
        request = orchestrator_api.TrialRewardRequest()

        for dest_actor in self._trial.get_actors(pattern_list=to):
            reward = common_api.Reward(receiver_name=dest_actor.name, tick_id=-1, value=value)
            reward_source = common_api.RewardSource(sender_name=self.name, value=value, confidence=confidence)
            if user_data is not None:
                reward_source.user_data.Pack(user_data)
            reward.sources.append(reward_source)
            request.rewards.append(reward)

        if request.rewards:
            metadata = (("trial-id", self.get_trial_id()), ("actor-name", self.name))
            self._actor_sub.SendReward(request=request, metadata=metadata)

    def send_message(self, payload, to, to_environment=False):
        message_req = orchestrator_api.TrialMessageRequest()

        for dest_actor in self._trial.get_actors(pattern_list=to):
            message = common_api.Message(tick_id=-1, receiver_name=dest_actor.name)
            if payload is not None:
                message.payload.Pack(payload)
            message_req.messages.append(message)

        if to_environment:
            message = common_api.Message(tick_id=-1, receiver_name=ENVIRONMENT_ACTOR_NAME)
            if payload is not None:
                message.payload.Pack(payload)
            message_req.messages.append(message)

        if message_req.messages:
            metadata = (("trial-id", self.get_trial_id()), ("actor-name", self.name))
            self._actor_sub.SendMessage(request=message_req, metadata=metadata)

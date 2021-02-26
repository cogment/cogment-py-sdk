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
from abc import ABC
from cogment.session import Session, EventType

import cogment.api.orchestrator_pb2 as orchestrator_api
import cogment.api.common_pb2 as common_api


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
        self.name = id
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
            setattr(self, a_c.name, a_c)

    def __iter__(self):
        return iter(self._actor_classes_list)

    def __contains__(self, key):
        return hasattr(self, key)

    def __getitem__(self, key):
        return getattr(self, key)

    def get_class_by_index(self, index):
        return self._actor_classes_list[index]


class ActorSession(Session):
    """This represents an actor being performed locally."""

    def __init__(self, impl, actor_class, trial, name, impl_name, config):
        super().__init__(trial)
        self.class_name = actor_class.name
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
            try:
                event = await self.__event_queue.get()

            except asyncio.CancelledError as exc:
                logging.debug(f"Coroutine for actor [{self.name}] cancelled while waiting for an event")
                break

            self._last_event_received = (event.type == EventType.FINAL)
            keep_looping = yield event
            self.__event_queue.task_done()
            loop_active = (keep_looping is None or bool(keep_looping)) and not self._last_event_received
            if not loop_active:
                if self._last_event_received:
                    self._ended = True
                    logging.debug(f"Last event received, exiting event loop for actor [{self.name}]")
                else:
                    logging.debug(f"End of event loop for actor [{self.name}] requested by user")

        logging.debug(f"Exiting actor [{self.name}] event loop generator")

    def do_action(self, action):
        assert self.__started
        self._action_queue.put_nowait(action)

    async def _retrieve_action(self):
        action = await self._action_queue.get()
        self._action_queue.task_done()
        return action

    def _new_event(self, event):
        if not self.__started or self._ended:
            return

        if self.__event_queue:
            self.__event_queue.put_nowait(event)
        else:
            logging.warning(f"Actor [{self.name}] received an event that it was unable to handle.")

    async def _run(self):
        try:
            await self.__impl(self)

        except asyncio.CancelledError:
            logging.debug(f"Actor [{self.name}] implementation coroutine cancelled")

        except Exception:
            logging.error(f"An exception occured in user actor implementation [{self.impl_name}]:\n"
                          f"{traceback.format_exc()}")
            raise


class _ServedActorSession(ActorSession):
    def __init__(self, impl, actor_class, trial, name, impl_name, config):
        super().__init__(impl, actor_class, trial, name, impl_name, config)

    def add_reward(self, value, confidence, to, tick_id=-1, user_data=None):
        assert self._trial is not None
        self._trial.add_reward(value, confidence, to, tick_id, user_data)

    def send_message(self, payload, to, to_environment=False):
        assert self._trial is not None
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
            metadata = (("trial-id", self.get_trial_id()), ("actor-name", self.name))
            self._actor_sub.SendReward(request=request, metadata=metadata)

    def send_message(self, payload, to, to_environment=False):
        message_req = orchestrator_api.TrialMessageRequest()
        for dest_actor in self._trial.get_actors(pattern_list=to):
            message = common_api.Message(tick_id=-1, receiver_name=dest_actor.name)
            if payload is not None:
                message.payload.Pack(payload)
            message_req.messages.append(message)
            metadata = (("trial-id", self.get_trial_id()), ("actor-name", self.name))
            self._actor_sub.SendMessage(request=message_req, metadata=metadata)

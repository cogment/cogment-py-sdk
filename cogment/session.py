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

from cogment.errors import CogmentError
from cogment.utils import logger

from abc import ABC
from enum import Enum
import asyncio


# This class is not necessary, but simplifies the code as it is.
# I.e. the actual init_output proto message could be sent instead.
class _InitAck:
    """Internal class to signal acknowledgement of the start."""
    pass


class _Ending:
    """Internal class to signal the ending."""
    pass


class _EndingAck:
    """Internal class to signal acknowledgement of the ending."""
    pass


class ActorInfo:
    """Class representing the information of an actor."""

    def __init__(self, name, class_name):
        self.actor_name = name
        self.actor_class_name = class_name

    def __str__(self):
        result = f"ActorInfo: actor_name = {self.actor_name}, actor_class_name = {self.actor_class_name}"
        return result


class RecvObservation:
    """Class representing a received observation in a trial."""

    def __init__(self, obs, obs_space):
        self.tick_id = obs.tick_id
        self.timestamp = obs.timestamp
        self.observation = obs_space

    def __str__(self):
        result = f"RecvObservation: tick_id = {self.tick_id}, timestamp = {self.timestamp}"
        result += f", observation = {self.observation}"
        return result

    @property
    def snapshot(self):
        logger.deprecated(f"Deprecated use of 'snapshot' in RecvObservation. Use 'observation' instead.")
        return self.observation

    @snapshot.setter
    def snapshot(self, val):
        logger.deprecated(f"Deprecated use of 'snapshot' in RecvObservation. Use 'observation' instead.")
        self.observation = val


class ActorStatus(Enum):
    """Enum class for the status of actors in a trial."""

    UNKNOWN = 0
    ACTIVE = 1
    UNAVAILABLE = 2
    DEFAULT = 3


class RecvAction:
    """Class representing a received action in a trial."""

    def __init__(self, actor_index, tick_id, status, timestamp, action):
        self.tick_id = tick_id
        self.actor_index = actor_index
        self.status = status
        self.timestamp = timestamp
        self.action = action

    def __str__(self):
        result = f"RecvAction: tick_id = {self.tick_id}, actor_index = {self.actor_index}"
        result += f", status = {self.status}, timestamp = {self.timestamp}, action = {self.action}"
        return result


class RecvRewardSource:
    """Class representing a received reward source in a trial."""

    def __init__(self, src):
        self.value = src.value
        self.confidence = src.confidence
        self.sender_name = src.sender_name
        self.user_data = src.user_data

    def __str__(self):
        result = f"RecvRewardSource: value = {self.value}, confidence = {self.confidence}"
        result += f", sender_name = {self.sender_name}, user_data = {self.user_data}"
        return result


class RecvReward:
    """Class representing a received reward in a trial."""

    def __init__(self, reward):
        self.receiver_name = reward.receiver_name
        self.tick_id = reward.tick_id
        self.value = reward.value
        self._sources = reward.sources

    def get_nb_sources(self):
        return len(self._sources)

    def all_sources(self):
        if not self._sources:
            raise CogmentError("Unexpected reward with no source")
        for src in self._sources:
            yield RecvRewardSource(src)

    def __str__(self):
        result = f"RecvReward: tick_id = {self.tick_id}, receiver_name = {self.receiver_name}"
        result += f", value = {self.value}, sources = {self._sources}"
        return result


class RecvMessage:
    """Class representing a received message in a trial."""

    def __init__(self, message):
        self.receiver_name = message.receiver_name
        self.tick_id = message.tick_id
        self.sender_name = message.sender_name
        self.payload = message.payload

    def __str__(self):
        result = f"RecvMessage: tick_id = {self.tick_id}, receiver_name = {self.receiver_name}"
        result += f", sender_name = {self.sender_name}, payload = {self.payload}"
        return result


class EventType(Enum):
    """Enum class for the types of received events in a trial."""

    NONE = 0
    ACTIVE = 1
    ENDING = 2
    FINAL = 3


class RecvEvent:
    """Class representing a received event in a trial."""

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
    """Base class representing the session of an actor or environment for a trial."""

    def __init__(self, trial, name, impl, impl_name, config):
        self._trial = trial
        self.name = name
        self.impl_name = impl_name
        self._impl = impl
        self.config = config
        self._incoming_event_queue = asyncio.Queue()
        self._outgoing_data_queue = asyncio.Queue()
        self._started = False
        self._last_tick_delivered = -1
        self._last_event_delivered = False
        self._user_task = None  # Task used to call user implementation
        self._auto_ack = True

        # Pre-compute since it will be used regularly
        self._active_actors = [ActorInfo(actor.name, actor.actor_class.name) for actor in trial.actors]

    def __str__(self):
        result = f"Session: name = {self.name}, impl_name = {self.impl_name}, config = {self.config}"
        result += f", trial = {self._trial}"
        return result

    def _start(self, auto_done_sending):
        if self._started:
            raise CogmentError(f"Cannot start [{self.name}] more than once.")
        if self._trial.ended:
            raise CogmentError(f"Cannot start [{self.name}] because the trial has ended.")

        self._auto_ack = auto_done_sending
        self._started = True
        self._post_outgoing_data(_InitAck())

    def _exit_queues(self):
        self._incoming_event_queue.put_nowait(None)
        self._outgoing_data_queue.put_nowait(None)

    async def _run(self):
        try:
            await self._impl(self)
            return True

        except asyncio.CancelledError as exc:
            logger.debug(f"[{self.name}] implementation coroutine cancelled: [{exc}]")
            return False

        except Exception:
            logger.exception(f"An exception occured in user implementation of [{self.name}]")
            raise

    def _start_user_task(self):
        self._user_task = asyncio.create_task(self._run())
        return self._user_task

    def _post_incoming_event(self, event_tuple):
        """event_tuple is a tuple (tick_id, event)"""
        if not self._started:
            logger.warning(f"[{self.name}] received an event before session was started.")
            return
        if self._trial.ended:
            logger.debug(f"Event received after trial is over: [{event_tuple}]")
            return

        self._incoming_event_queue.put_nowait(event_tuple)

    def _post_outgoing_data(self, data):
        if not self._started:
            logger.warning(f"Trial [{self._trial.id}] - Session for [{self.name}]: "
                           f"Cannot send until session is started.")
            return
        if self._trial.ending_ack:
            logger.warning(f"Trial [{self._trial.id}] - Session for [{self.name}]: "
                           f"Cannot send after acknowledging ending")
            return

        if data is None:
            raise CogmentError(f"Trial [{self._trial.id}] - Session for [{self.name}]: Data posted is `None`")

        if type(data) == _Ending:
            self._trial.ending = True
        elif type(data) == _EndingAck:
            self._trial.ending_ack = True

        self._outgoing_data_queue.put_nowait(data)

    async def _retrieve_outgoing_data(self):
        try:
            while True:
                data = await self._outgoing_data_queue.get()
                if data is None:
                    logger.debug(f"Trial [{self._trial.id}] - Session for [{self.name}]: "
                                 f"Forcefull data loop exit")
                    break
                yield data
                self._outgoing_data_queue.task_done()

        except RuntimeError as exc:
            # Unfortunatelty asyncio returns a standard RuntimeError in this case
            if exc.args[0] != "Event loop is closed":
                raise
            else:
                logger.debug(f"Trial [{self._trial.id}] - Session for [{self.name}]: "
                             f"Normal exception on retrieving data at close: [{exc}]")

        except asyncio.CancelledError as exc:
            logger.debug(f"Trial [{self._trial.id}] - Session for [{self.name}]: "
                         f"data retrieval coroutine cancelled: [{exc}]")

        logger.debug(f"Exiting [{self.name}] _retrieve_outgoing_data loop generator")

    def get_trial_id(self):
        return self._trial.id

    def get_tick_id(self):
        return self._trial.tick_id

    def is_trial_over(self):
        return self._trial.ended

    def sending_done(self):
        if self._auto_ack:
            raise CogmentError("Cannot manually end sending as it is set to automatic")
        elif not self._trial.ending:
            raise CogmentError("Cannot stop sending before trial is ready to end")
        elif self._trial.ended:
            logger.warning(f"Trial [{self._trial.id}] - Session [{self.name}] "
                           f"end sending ignored because the trial has already ended.")
        elif self._trial.ending_ack:
            logger.debug(f"Trial [{self._trial.id}] - Session [{self.name}] cannot end sending more than once")
        else:
            self._post_outgoing_data(_EndingAck())

    async def all_events(self):
        if not self._started:
            logger.warning(f"Cannot retrieve events until [{self.name}] is started.")
            return
        if self._trial.ended:
            logger.info(f"No more events for [{self.name}] because the trial has ended.")
            return

        logger.debug(f"Trial [{self._trial.id}] - Session [{self.name}] starting event loop")

        loop_active = not self._last_event_delivered
        while loop_active:
            try:
                event_tuple = await self._incoming_event_queue.get()
                if event_tuple is None:
                    logger.debug(f"Trial [{self._trial.id}] - Session [{self.name}]: "
                                 f"Forcefull event loop exit")
                    self._last_event_delivered = True
                    break

            except asyncio.CancelledError as exc:
                logger.debug(f"[{self.name}] coroutine cancelled while waiting for an event: [{exc}]")
                break

            tick_id, event = event_tuple
            if tick_id >= 0:
                self._last_tick_delivered = tick_id
            self._last_event_delivered = (event.type == EventType.FINAL)

            keep_looping = yield event
            self._incoming_event_queue.task_done()

            loop_active = (keep_looping is None or bool(keep_looping)) and not self._last_event_delivered
            if not loop_active:
                if self._last_event_delivered:
                    logger.debug(f"Last event delivered, exiting [{self.name}] event loop")
                else:
                    logger.debug(f"End of event loop for [{self.name}] requested by user")

        logger.debug(f"Exiting [{self.name}] event loop generator")

    async def event_loop(self):
        logger.deprecated("`event_loop` is deprecated. Use `all_events` instead.")

        async for event in self.all_events():
            yield event

    def add_reward(self, value, confidence, to, tick_id=-1, user_data=None):
        if not self._started:
            logger.warning(f"Trial [{self._trial.id}] - Session for [{self.name}]: "
                           f"Cannot send reward until session is started.")
            return
        if self._trial.ending_ack:
            logger.warning(f"Trial [{self._trial.id}] - Session for [{self.name}]: "
                           f"Cannot send reward after acknowledging ending.")
            return

        for dest in to:
            reward = common_api.Reward(receiver_name=dest, tick_id=tick_id, value=value)
            reward_source = common_api.RewardSource(sender_name=self.name, value=value, confidence=confidence)
            if user_data is not None:
                reward_source.user_data.Pack(user_data)
            reward.sources.append(reward_source)

            self._post_outgoing_data(reward)

    def _send_message(self, payload, to):
        if not self._started:
            logger.warning(f"Trial [{self._trial.id}] - Session for [{self.name}]: "
                           f"Cannot send message until session is started.")
            return
        if self._trial.ending_ack:
            logger.warning(f"Trial [{self._trial.id}] - Session for [{self.name}]: "
                           f"Cannot send message after acknowledging ending.")
            return

        for dest in to:
            message = common_api.Message(tick_id=-1, receiver_name=dest)
            if payload is not None:
                message.payload.Pack(payload)

            self._post_outgoing_data(message)

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

import grpc
import grpc.aio  # type: ignore

import cogment.api.common_pb2 as common_api
import cogment.api.trial_datastore_pb2 as datastore_api

from cogment.control import TrialState
from cogment.parameters import TrialParameters
from cogment.errors import CogmentError
from cogment.utils import logger

import asyncio
import enum
import datetime

_REV_NANO = 1.0 / 1_000_000_000


class DatastoreFields(enum.Enum):
    """Enum class for the different fields of the actor data that can be retrieved."""

    UNKNOWN = datastore_api.StoredTrialSampleField.STORED_TRIAL_SAMPLE_FIELD_UNKNOWN
    OBSERVATION = datastore_api.StoredTrialSampleField.STORED_TRIAL_SAMPLE_FIELD_OBSERVATION
    ACTION = datastore_api.StoredTrialSampleField.STORED_TRIAL_SAMPLE_FIELD_ACTION
    REWARD = datastore_api.StoredTrialSampleField.STORED_TRIAL_SAMPLE_FIELD_REWARD
    RECEIVED_REWARDS = datastore_api.StoredTrialSampleField.STORED_TRIAL_SAMPLE_FIELD_RECEIVED_REWARDS
    SENT_REWARDS = datastore_api.StoredTrialSampleField.STORED_TRIAL_SAMPLE_FIELD_SENT_REWARDS
    RECEIVED_MESSAGES = datastore_api.StoredTrialSampleField.STORED_TRIAL_SAMPLE_FIELD_RECEIVED_MESSAGES
    SENT_MESSAGES = datastore_api.StoredTrialSampleField.STORED_TRIAL_SAMPLE_FIELD_SENT_MESSAGES


class DatastoreTrialInfo:
    """Class representing trial info."""

    def __init__(self, cog_settings, info: datastore_api.StoredTrialInfo):
        self.trial_id = info.trial_id
        self.trial_state = TrialState(info.last_state)
        self.user_id = info.user_id
        self.sample_count = info.samples_count

        self.parameters = TrialParameters(None)
        self.parameters._set(cog_settings, info.params)

    def __str__(self):
        result = f"DatastoreTrialInfo:"
        result += f" trial_id = {self.trial_id}, trial_state = {self.trial_state}"
        result += f", user_id = {self.user_id}, sample_count = {self.sample_count}"
        result += f", parameters = {self.parameters}"
        return result


class DatastoreReward:
    """Class representing an individual reward sent during this sample."""

    def __init__(self, reward, payloads, parameters: TrialParameters):
        self._raw_reward = reward
        self._payloads = payloads
        self._parameters = parameters

        self.value = self._raw_reward.reward
        self.confidence = self._raw_reward.confidence

    def __str__(self):
        result = f"DatastoreReward:"
        result += f" value = {self.value}, confidence = {self.confidence}"
        result += f", sender = {self.sender}, receiver = {self.receiver}, user_data = {self.user_data}"
        return result

    @property
    def sender(self):
        """Name of actor that sent the reward"""
        actor_index = self._raw_reward.sender
        return self._parameters.actors[actor_index].name

    @property
    def receiver(self):
        """Name of actor that received the reward"""
        actor_index = self._raw_reward.receiver
        return self._parameters.actors[actor_index].name

    @property
    def user_data(self):
        """User data sent with the reward"""
        if self._raw_reward.HasField("user_data"):
            data_index = self._raw_reward.user_data
            data_content = self._payloads[data_index]
            any = common_api.RewardSource().user_data  # Easier than instantiating 'google.protobuf.any_pb2.Any'
            any.ParseFromString(data_content)

            return any
        else:
            return None


class DatastoreMessage:
    """Class representing an individual message sent during this sample."""

    def __init__(self, message, payloads, parameters: TrialParameters):
        self._raw_message = message
        self._payloads = payloads
        self._parameters = parameters

    def __str__(self):
        result = f"DatastoreMessage:"
        result += f", sender = {self.sender}, receiver = {self.receiver}, payload = {self.payload}"
        return result

    @property
    def sender(self):
        """Name of actor that sent the message"""
        actor_index = self._raw_message.sender
        return self._parameters.actors[actor_index].name

    @property
    def receiver(self):
        """Name of actor that received the message"""
        actor_index = self._raw_message.receiver
        return self._parameters.actors[actor_index].name

    @property
    def payload(self):
        """Payload sent with the reward"""
        if self._raw_message.HasField("payload"):
            payload_index = self._raw_message.payload
            payload_content = self._payloads[payload_index]
            any = common_api.Message().payload  # Easier than instantiating 'google.protobuf.any_pb2.Any'
            any.ParseFromString(payload_content)

            return any
        else:
            return None


class DatastoreActorData:
    """Class representing the data for an actor in a sample."""

    def __init__(self, sample, payloads, parameters: TrialParameters):
        self._raw_sample = sample
        self._payloads = payloads
        self._parameters = parameters

    def __str__(self):
        result = f"DatastoreActorData:"
        result += f" name = {self.name}, reward = {self.reward}"
        result += f", observation = {self.observation}, action = {self.action}"
        result += f", nb received rewards = {len(self._raw_sample.received_rewards)}"
        result += f", nb sent rewards = {len(self._raw_sample.sent_rewards)}"
        result += f", nb received messages = {len(self._raw_sample.received_messages)}"
        result += f", nb sent messages = {len(self._raw_sample.sent_messages)}"
        return result

    @property
    def name(self):
        """Name of the actor"""
        actor_index = self._raw_sample.actor
        return self._parameters.actors[actor_index].name

    @property
    def observation(self):
        """Observation space to the actor"""
        if self._raw_sample.HasField("observation"):
            actor_index = self._raw_sample.actor
            obs_space = self._parameters.actors[actor_index]._actor_class.observation_space()

            obs_index = self._raw_sample.observation
            obs_content = self._payloads[obs_index]
            obs_space.ParseFromString(obs_content)
            return obs_space
        else:
            return None

    @property
    def action(self):
        """Action space from the actor"""
        if self._raw_sample.HasField("action"):
            actor_index = self._raw_sample.actor
            action_space = self._parameters.actors[actor_index]._actor_class.action_space()

            action_index = self._raw_sample.action
            action_content = self._payloads[action_index]
            action_space.ParseFromString(action_content)
            return action_space
        else:
            return None

    @property
    def reward(self):
        """Aggregated reward received by the actor"""
        if self._raw_sample.HasField("reward"):
            return self._raw_sample.reward
        else:
            return None

    def all_received_rewards(self):
        for rew in self._raw_sample.received_rewards:
            yield DatastoreReward(rew, self._payloads, self._parameters)

    def all_sent_rewards(self):
        for rew in self._raw_sample.sent_rewards:
            yield DatastoreReward(rew, self._payloads, self._parameters)

    def all_received_messages(self):
        for msg in self._raw_sample.received_messages:
            yield DatastoreMessage(msg, self._payloads, self._parameters)

    def all_sent_messages(self):
        for msg in self._raw_sample.sent_messages:
            yield DatastoreMessage(msg, self._payloads, self._parameters)


class DatastoreSample:
    """Class representing a trial sample from the trial datastore service."""

    def __init__(self, sample, params: TrialParameters):
        self.trial_id = sample.trial_id
        self.trial_state = TrialState(sample.state)
        self.tick_id = sample.tick_id
        self.timestamp = sample.timestamp

        self._raw_sample = sample
        self._parameters = params

        self.actors_data = {}
        for smpl in self._raw_sample.actor_samples:
            data = DatastoreActorData(smpl, self._raw_sample.payloads, self._parameters)
            self.actors_data[data.name] = data
        if len(self.actors_data) != len(self._raw_sample.actor_samples):
            raise CogmentError(f"Duplicate actor names in datastore sample")

    def __str__(self):
        utc_time = datetime.datetime.utcfromtimestamp(self.timestamp * _REV_NANO)
        result = f"DatastoreSample:"
        result += f" trial_id = {self.trial_id}, trial_state = {self.trial_state}"
        result += f", tick_id = {self.tick_id}, timestamp = {self.timestamp} UTC[{utc_time}]"
        result += f", nb actors = {len(self.actors_data)}"
        return result


class Datastore:
    """Class representing the session of a datalog for a trial."""

    def __init__(self, stub, cog_settings):
        self._datastore_stub = stub
        self._cog_settings = cog_settings
        self._timeout = 0

    def __str__(self):
        result = f"Datastore"
        return result

    async def all_trials(self, bundle_size=1):
        request = datastore_api.RetrieveTrialsRequest()
        request.timeout = 0
        request.trials_count = bundle_size
        request.trial_handle = ""

        while True:
            reply = await self._datastore_stub.RetrieveTrials(request)

            for rep_info in reply.trial_infos:
                info = DatastoreTrialInfo(self._cog_settings, rep_info)
                yield info

            if len(reply.trial_infos) < bundle_size:
                break
            if reply.next_trial_handle:
                request.trial_handle = reply.next_trial_handle
            else:
                break

    async def get_trials(self, ids):
        request = datastore_api.RetrieveTrialsRequest()
        request.timeout = self._timeout
        for id in ids:
            request.trial_ids.append(id)

        reply = await self._datastore_stub.RetrieveTrials(request)

        trial_infos = []
        for rep_info in reply.trial_infos:
            info = DatastoreTrialInfo(self._cog_settings, rep_info)
            trial_infos.append(info)

        return trial_infos

    async def delete_trials(self, ids):
        if not ids:
            raise CogmentError("At least one trial ID must be provided to delete")

        request = datastore_api.DeleteTrialsRequest()
        for id in ids:
            request.trial_ids.append(id)

        await self._datastore_stub.DeleteTrials(request)

    async def all_samples(self, trial_infos, actor_names=[], actor_classes=[], actor_implementations=[], fields=[]):
        if not trial_infos:
            raise CogmentError("At least one trial info must be provided to retrieve samples")

        request = datastore_api.RetrieveSamplesRequest()

        params = {}
        for info in trial_infos:
            request.trial_ids.append(info.trial_id)
            params[info.trial_id] = info.parameters
        for name in actor_names:
            request.actor_names.append(name)
        for cls in actor_classes:
            request.actor_classes.append(cls)
        for impl in actor_implementations:
            request.actor_implementations.append(impl)
        for enum_field in fields:
            request.selected_sample_fields.append(enum_field.value)

        reply_itor = self._datastore_stub.RetrieveSamples(request)
        if not reply_itor:
            raise CogmentError(f"'all_samples' failed to connect")

        try:
            async for reply in reply_itor:
                raw_sample = reply.trial_sample
                param = params[raw_sample.trial_id]
                sample = DatastoreSample(raw_sample, param)
                keep_looping = yield sample
                if keep_looping is not None and not bool(keep_looping):
                    break

        except grpc.aio.AioRpcError as exc:
            logger.debug(f"gRPC failed status details: [{exc.debug_error_string()}]")
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                logger.error(f"Datastore all_samples communication lost: [{exc.details()}]")
            else:
                logger.exception("Datastore all_samples -- Unexpected aio failure")
                raise

        except GeneratorExit:
            raise

        except asyncio.CancelledError as exc:
            logger.debug(f"Datastore all_samples coroutine cancelled while waiting for samples: [{exc}]")

        except Exception:
            logger.exception("Datastore all_samples")
            raise

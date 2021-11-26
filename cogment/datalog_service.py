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

import grpc.aio  # type: ignore

import cogment.api.datalog_pb2_grpc as datalog_grpc_api
import cogment.api.common_pb2 as common_api
import cogment.api.datalog_pb2 as datalog_api

from cogment.control import TrialState
from cogment.datalog import DatalogSession
from cogment.errors import CogmentError
from cogment.utils import list_versions
from cogment.session import RecvObservation, RecvAction, RecvMessage, RecvReward

import logging
import asyncio


class LogParams:
    """Class representing the parameters of a trial for the datalog service."""

    def __init__(self, cog_settings):
        self.max_steps = None
        self.max_inactivity = None
        self.datalog = None
        self.environment = None
        self.nb_actors = None

        self._actor_indexes = None
        self._raw_params = None
        self._settings = cog_settings

    def __str__(self):
        result = f"LogParams: {self._raw_params}"
        return result

    # Type of serialized data being produced and consumed by this class.
    # This is dependent on all the underlying protobuf messages used to
    # serialize/deserialize, and should be incremented if any of them changes in
    # a backward or forward incompatible way. API 1.0 could be considered a type 0 or 1.
    # Current dependencies: TrialParams, DatalogParams, EnvironmentParams, ActorParams,
    #                       TrialConfig, EnvironmentConfig, ActorConfig
    def get_serialization_type(self):
        return 2

    def _set(self, raw_params):
        self._set_from_params(raw_params)

    def serialize(self):
        if self._raw_params is None:
            raise CogmentError("Not set, cannot serialize")
        return self._raw_params.SerializeToString()

    def deserialize(self, raw_string):
        params = common_api.TrialParams()
        params.ParseFromString(raw_string)
        self._set_from_params(params)

    def _set_from_params(self, raw_params):
        if type(raw_params) != common_api.TrialParams:
            raise CogmentError(f"Wrong type of parameters provided [{type(raw_params)}]")

        self.max_steps = raw_params.max_steps
        self.max_inactivity = raw_params.max_inactivity

        self.datalog = {
            "endpoint": raw_params.datalog.endpoint,
            "exclude": raw_params.datalog.exclude_fields,
        }

        self.environment = {
            "name": raw_params.environment.name,
            "endpoint": raw_params.environment.endpoint,
            "implementation": raw_params.environment.implementation,
        }

        self.nb_actors = len(raw_params.actors)
        self._actor_indexes = None
        self._raw_params = raw_params

    def get_trial_config(self):
        config = None
        if self._raw_params.HasField("trial_config"):
            config = self._settings.trial.config_type()
            config.ParseFromString(self._raw_params.trial_config.content)

        return config

    def get_environment_config(self):
        config = None
        if(self._raw_params.environment.HasField("config")):
            config = self._settings.environment.config_type()
            config.ParseFromString(self._raw_params.environment.config.content)

        return config

    def get_actor_index(self, actor_name):
        if self._actor_indexes is not None:
            return self._actor_indexes.get(actor_name)
        else:
            indexes = {}
            for index, actor in enumerate(self._raw_params.actors):
                indexes[actor.name] = index
            self._actor_indexes = indexes
            return indexes.get(actor_name)

    def get_actor_name(self, actor_index):
        return self._raw_params.actors[actor_index].name

    def get_actor(self, actor_index):
        actor = self._raw_params.actors[actor_index]

        actor_config = None
        a_c = self._settings.actor_classes.__getattribute__(actor.actor_class)
        if actor.HasField("config"):
            actor_config = a_c.config_type()
            actor_config.ParseFromString(actor.config.content)

        actor_data = {
            "name": actor.name,
            "actor_class": actor.actor_class,
            "endpoint": actor.endpoint,
            "implementation": actor.implementation,
            "config": actor_config,
            "action_space": a_c.action_space,
            "observation_space": a_c.observation_space,
        }

        return actor_data


class LogSample:
    """Class representing a trial sample for the datalog service."""

    def __init__(self, params):
        self.tick_id = None
        self.timestamp = None
        self.state = None
        self.events = None

        self._raw_sample = None

        if type(params) != LogParams:
            raise CogmentError(f"Wrong type of params provided [{type(params)}]")
        self._params = params

    def __str__(self):
        result = f"LogSample: {self._raw_sample}"
        return result

    # Type of serialized data being produced and consumed by this class.
    # This is dependent on all the underlying protobuf messages used to
    # serialize/deserialize, and should be incremented if any of them changes in
    # a backward or forward incompatible way. API 1.0 could be considered a type 0 or 1.
    # Current dependencies: DatalogSample, SampleInfo, TrialState, ObservationSet,
    #                       Action, Reward, RewardSource, Message
    def get_serialization_type(self):
        return 2

    def _set(self, raw_sample):
        self._set_from_sample(raw_sample)

    def serialize(self):
        if self._raw_sample is None:
            raise CogmentError("Not set, nothing to serialize")
        return self._raw_sample.SerializeToString()

    def deserialize(self, raw_string):
        sample = datalog_api.DatalogSample()
        sample.ParseFromString(raw_string)
        self._set_from_sample(sample)

    def _set_from_sample(self, sample):
        if type(sample) != datalog_api.DatalogSample:
            raise CogmentError(f"Wrong type of sample provided [{type(sample)}]")
        if sample.HasField("info"):
            self.state = TrialState(sample.info.state)
            self.tick_id = sample.info.tick_id
            self.timestamp = sample.info.timestamp
            self.events = sample.info.special_events
        else:
            self.state = None
            self.tick_id = None
            self.timestamp = None
            self.events = None

        self._raw_sample = sample

    def all_actor_names(self):
        for index in range(self._params.nb_actors):
            yield self._params.get_actor_name(index)

    def get_action(self, actor):
        if isinstance(actor, int):
            actor_index = actor
        elif isinstance(actor, str):
            actor_index = self._params.get_actor_index(actor)
        else:
            raise CogmentError(f"Wrong type of actor parameter [{type(actor)}]: must be int or str")
        if actor_index is None or actor_index < 0 or actor_index >= self._params.nb_actors:
            raise CogmentError(f"Invalid actor [{actor}] [{actor_index}]")

        if len(self._raw_sample.actions) > 0:
            data = self._raw_sample.actions[actor_index]
            action = self._params.get_actor(actor_index)["action_space"]()
            action.ParseFromString(data.content)
            return RecvAction(actor_index, data, action)
        else:
            return None

    def get_observation(self, actor):
        if isinstance(actor, int):
            actor_index = actor
        elif isinstance(actor, str):
            actor_index = self._params.get_actor_index(actor)
        else:
            raise CogmentError(f"Wrong type of actor parameter [{type(actor)}]: must be int or str")
        if actor_index is None or actor_index < 0 or actor_index >= self._params.nb_actors:
            raise CogmentError(f"Invalid actor [{actor}] [{actor_index}]")

        if self._raw_sample.HasField("observations"):
            data = self._raw_sample.observations
            obs_index = data.actors_map[actor_index]
            obs_content = data.observations[obs_index]
            obs = self._params.get_actor(actor_index)["observation_space"]()
            obs.ParseFromString(obs_content)
            return RecvObservation(data, obs)
        else:
            return None

    def all_rewards(self):
        for rew in self._raw_sample.rewards:
            yield RecvReward(rew)

    def all_messages(self):
        for msg in self._raw_sample.messages:
            yield RecvMessage(msg)


async def _read_sample(context, session, settings):
    try:
        while True:
            request = await context.read()

            if request == grpc.aio.EOF:
                logging.info(f"The orchestrator disconnected from LogExpoterService.")
                break

            elif request.HasField("sample"):
                trial_ended = (request.sample.info.state == common_api.TrialState.ENDED)
                sample = LogSample(session.trial_params)
                sample._set(request.sample)
                session._new_sample(sample)
                if trial_ended:
                    logging.debug("Last log sample received for trial")
                    break
            else:
                logging.warning(f"Invalid request received from the orchestrator : {request}")

    except asyncio.CancelledError as exc:
        logging.debug(f"DatalogServicer '_read_sample' coroutine cancelled: [{exc}]")
        raise

    except Exception:
        logging.exception("_read_sample")
        raise

    # Exit the loop
    session._new_sample(None)


class DatalogServicer(datalog_grpc_api.DatalogSPServicer):
    """Internal datalog servicer class."""

    def __init__(self, impl, cog_settings):
        self._impl = impl
        self.__cog_settings = cog_settings
        logging.info("Datalog Service started")

    # Override
    async def RunTrialDatalog(self, request_iterator, context):
        reader_task = None
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]
            user_id = metadata["user-id"]

            request = await context.read()

            if not request.HasField("trial_params"):
                raise CogmentError(f"Initial logging request for [{trial_id}] does not contain parameters.")

            trial_params = LogParams(self.__cog_settings)
            trial_params._set(request.trial_params)

            session = DatalogSession(self._impl, trial_id, user_id, trial_params)
            user_task = session._start_user_task()

            reader_task = asyncio.create_task(_read_sample(context, session, self.__cog_settings))

            normal_return = await user_task

            if normal_return:
                logging.debug(f"User datalog implementation returned")
            else:
                logging.debug(f"User datalog implementation was cancelled")

        except asyncio.CancelledError as exc:
            logging.debug(f"Datalog implementation coroutine cancelled: [{exc}]")

        except Exception:
            logging.exception("RunTrialDatalog")
            raise

        finally:
            if reader_task is not None:
                reader_task.cancel()

    # Override
    async def Version(self, request, context):
        try:
            return list_versions()
        except Exception:
            logging.exception("Version")
            raise

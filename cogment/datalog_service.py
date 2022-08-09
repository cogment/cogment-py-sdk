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
from cogment.datalog import DatalogSession, LogParams
from cogment.parameters import TrialParameters
from cogment.errors import CogmentError
from cogment.utils import list_versions, logger
from cogment.session import RecvObservation, ActorStatus, RecvAction, RecvMessage, RecvReward

import asyncio


class LogSample:
    """Class representing a trial sample for the datalog service."""

    def __init__(self, params):
        self.tick_id = None
        self.out_of_sync = None
        self.timestamp = None
        self.state = None
        self.events = None

        self._raw_sample = None
        self._actor_indexes = None

        self._log_params = None
        self._parameters = None
        if type(params) == LogParams:
            logger.deprecated(f"Deprecated use of LogParams")
            self._log_params = params
            self._nb_actors = params.nb_actors
        elif type(params) == TrialParameters:
            self._parameters = params
            self._nb_actors = len(params.actors)
        else:
            raise CogmentError(f"Wrong type of params provided [{type(params)}]")

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
            self.out_of_sync = sample.info.out_of_sync
            self.tick_id = sample.info.tick_id
            self.timestamp = sample.info.timestamp
            self.events = sample.info.special_events
        else:
            self.state = None
            self.out_of_sync = None
            self.tick_id = None
            self.timestamp = None
            self.events = None

        self._raw_sample = sample

    def _get_actor_index(self, actor_name):
        if self._actor_indexes is None:
            indexes = {}
            if self._log_params:
                for index, actor in enumerate(self._log_params._raw_params.actors):
                    indexes[actor.name] = index
            else:
                for index, actor in enumerate(self._parameters.actors):
                    indexes[actor.name] = index
            self._actor_indexes = indexes

        return self._actor_indexes.get(actor_name)

    def all_actor_names(self):
        if self._log_params:
            for index in range(self._nb_actors):
                yield self._log_params.get_actor_name(index)
        else:
            for actor in self._parameters.actors:
                yield actor.name

    def get_action(self, actor):
        if isinstance(actor, int):
            actor_index = actor
        elif isinstance(actor, str):
            actor_index = self._get_actor_index(actor)
        else:
            raise CogmentError(f"Wrong type of actor parameter [{type(actor)}]: must be int or str")
        if actor_index is None or actor_index < 0 or actor_index >= self._nb_actors:
            raise CogmentError(f"Invalid actor [{actor}] [{actor_index}]")

        if len(self._raw_sample.actions) > 0:
            data = self._raw_sample.actions[actor_index]
            if actor_index in self._raw_sample.unavailable_actors:
                status = ActorStatus.UNAVAILABLE
                timestamp = 0
                action_space = None
            elif actor_index in self._raw_sample.default_actors:
                status = ActorStatus.DEFAULT
                timestamp = 0
                action_space = None
            else:
                status = ActorStatus.ACTIVE
                timestamp = data.timestamp
                if self._log_params:
                    action_space = self._log_params.get_actor(actor_index)["action_space"]()
                else:
                    action_space = self._parameters.actors[actor_index]._actor_class.action_space()
                action_space.ParseFromString(data.content)

            return RecvAction(actor_index, data.tick_id, status, timestamp, action_space)

        else:
            return None

    def get_observation(self, actor):
        if isinstance(actor, int):
            actor_index = actor
        elif isinstance(actor, str):
            actor_index = self._get_actor_index(actor)
        else:
            raise CogmentError(f"Wrong type of actor parameter [{type(actor)}]: must be int or str")
        if actor_index is None or actor_index < 0 or actor_index >= self._nb_actors:
            raise CogmentError(f"Invalid actor [{actor}] [{actor_index}]")

        if self._log_params:
            obs_space = self._log_params.get_actor(actor_index)["observation_space"]()
        else:
            obs_space = self._parameters.actors[actor_index]._actor_class.observation_space()

        if self._raw_sample.HasField("observations"):
            data = self._raw_sample.observations
            obs_index = data.actors_map[actor_index]
            obs_content = data.observations[obs_index]
            obs_space.ParseFromString(obs_content)
            return RecvObservation(data, obs_space)
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
                logger.info(f"The orchestrator disconnected from LogExpoterService.")
                break

            elif request.HasField("sample"):
                trial_ended = (request.sample.info.state == common_api.TrialState.ENDED)
                sample = LogSample(session.trial_parameters)
                sample._set(request.sample)
                session._new_sample(sample)
                if trial_ended:
                    logger.debug("Last log sample received for trial")
                    break
            else:
                logger.warning(f"Invalid request received from the orchestrator : {request}")

    except asyncio.CancelledError as exc:
        logger.debug(f"DatalogServicer '_read_sample' coroutine cancelled: [{exc}]")
        raise

    except Exception:
        logger.exception("_read_sample")
        raise

    # Exit the loop
    session._new_sample(None)


class DatalogServicer(datalog_grpc_api.DatalogSPServicer):
    """Internal datalog servicer class."""

    def __init__(self, impl, cog_settings):
        self._impl = impl
        self._cog_settings = cog_settings
        logger.info("Datalog Service started")

    # Override
    async def RunTrialDatalog(self, request_iterator, context):
        reader_task = None
        try:
            metadata = dict(context.invocation_metadata())
            trial_id = metadata["trial-id"]
            user_id = metadata["user-id"]

            request = await context.read()

            if not request.HasField("trial_params"):
                raise CogmentError(f"Initial data log request for [{trial_id}] does not contain parameters.")

            trial_parameters = TrialParameters(None)
            trial_parameters._set(self._cog_settings, request.trial_params)

            session = DatalogSession(self._impl, trial_id, user_id, trial_parameters)
            user_task = session._start_user_task()

            reader_task = asyncio.create_task(_read_sample(context, session, self._cog_settings))

            normal_return = await user_task

            if normal_return:
                logger.debug(f"User datalog implementation returned")
            else:
                logger.debug(f"User datalog implementation was cancelled")

        except asyncio.CancelledError as exc:
            logger.debug(f"Datalog implementation coroutine cancelled: [{exc}]")

        except Exception:
            logger.exception("RunTrialDatalog")
            raise

        finally:
            if reader_task is not None:
                reader_task.cancel()

    # Override
    async def Version(self, request, context):
        try:
            return list_versions()
        except Exception:
            logger.exception("Version")
            raise

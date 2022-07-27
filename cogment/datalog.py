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
from cogment.utils import logger
from cogment.errors import CogmentError

import asyncio


# Deprecated
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
        self._cog_settings = cog_settings

    def __str__(self):
        result = f"LogParams: {self._raw_params}"
        return result

    # Type of serialized data being produced and consumed by this class.
    # This is dependent on all the underlying protobuf messages used to
    # serialize/deserialize, and should be incremented if any of them changes in
    # a backward or forward incompatible way. API 1.0 could be considered a type 0 or 1.
    # Current dependencies: TrialParams, DatalogParams, EnvironmentParams, ActorParams,
    #                       SerializedMessage
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
            config = self._cog_settings.trial.config_type()
            config.ParseFromString(self._raw_params.trial_config.content)

        return config

    def get_environment_config(self):
        config = None
        if(self._raw_params.environment.HasField("config")):
            config = self._cog_settings.environment.config_type()
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
        a_c = self._cog_settings.actor_classes.__getattribute__(actor.actor_class)
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


class DatalogSession:
    """Class representing the session of a datalog for a trial."""

    def __init__(self, impl, trial_id, user_id, trial_parameters):
        self.trial_id = trial_id
        self.user_id = user_id
        self.trial_parameters = trial_parameters

        self._log_params = None
        self._user_task = None
        self._impl = impl
        self._queue = None

    def __str__(self):
        result = f"DatalogSession: trial_id = {self.trial_id}, user_id = {self.user_id}"
        result += f", trial_parameters = {self.trial_parameters}"
        return result

    def start(self):
        self._queue = asyncio.Queue()

    async def all_samples(self):
        if self._queue is not None:
            while True:
                try:
                    sample = await self._queue.get()
                    if sample is None:
                        break
                    keep_looping = yield sample
                    self._queue.task_done()
                    if keep_looping is not None and not bool(keep_looping):
                        break

                except asyncio.CancelledError as exc:
                    logger.debug(f"Datalog coroutine cancelled while waiting for a sample: [{exc}]")
                    break

    async def get_all_samples(self):
        logger.deprecated("'get_all_samples' is deprecated. Use 'all_samples' instead.")

        if self._queue is not None:
            while True:
                try:
                    sample = await self._queue.get()
                    if sample is None:
                        break
                    keep_looping = yield sample
                    self._queue.task_done()
                    if keep_looping is not None and not bool(keep_looping):
                        break

                except GeneratorExit:
                    raise

                except asyncio.CancelledError as exc:
                    logger.debug(f"Datalog coroutine cancelled while waiting for a sample: [{exc}]")
                    break

    def _new_sample(self, sample):
        if self._queue is not None:
            self._queue.put_nowait(sample)
        else:
            logger.warning("Datalog received a sample that it was unable to handle.")

    async def _run(self):
        try:
            await self._impl(self)
            return True

        except asyncio.CancelledError as exc:
            logger.debug(f"Datalog implementation coroutine cancelled: [{exc}]")
            return False

        except Exception:
            logger.exception(f"An exception occured in user datalog implementation:")
            raise

    def _start_user_task(self):
        self._user_task = asyncio.create_task(self._run())
        return self._user_task

    @property
    def trial_params(self):
        if self._log_params is None:
            logger.deprecated(f"DatalogSession's trial_params is deprecated")
            self._log_params = LogParams(self.trial_parameters._cog_settings)
            self._log_params._set(self.trial_parameters._raw_params)

        return self._log_params

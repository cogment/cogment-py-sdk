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

import cogment.api.environment_pb2 as env_api

from cogment.session import Session, _Ending, _EndingAck
from cogment.errors import CogmentError
from cogment.utils import logger

import time


class EnvironmentSession(Session):
    """Derived class representing the session of an environment for a trial."""

    def __init__(self, impl, trial, name, impl_name, config):
        super().__init__(trial, name, impl, impl_name, config)

    def __str__(self):
        result = super().__str__()
        result += f" --- EnvironmentSession: config = {self.config}"
        return result

    def get_active_actors(self):
        return self._active_actors

    def send_message(self, payload, to, to_environment=None):
        if to_environment is not None:
            logger.deprecated("Parameter 'to_environment' is deprecated for 'send_message' method. "
                              "No message will be sent back to the environment!")
        self._send_message(payload, to)

    def start(self, observations=None, auto_done_sending=True):
        self._start(auto_done_sending)

        if observations is not None:
            logger.debug(f"Trial [{self._trial.id}] - Environment [{self.name}] Sending first observation.")
            packed_obs = self._pack_observations(observations, -1)
            self._post_outgoing_data(packed_obs)

    def produce_observations(self, observations):
        if not self._trial.ended:
            packed_obs = self._pack_observations(observations, -1)
            self._post_outgoing_data(packed_obs)
            if self._trial.ending and self._auto_ack:
                self._post_outgoing_data(_EndingAck())
        else:
            logger.warning(f"Trial [{self._trial.id}] - Environment [{self.name}] "
                           f"Cannot send observation because the trial has ended.")

    def end(self, final_observations):
        if self._trial.ended:
            logger.warning(f"Trial [{self._trial.id}] - Environment [{self.name}] "
                           f"end request ignored because the trial has already ended.")
        elif self._trial.ending_ack:
            logger.warning(f"Trial [{self._trial.id}] - Environment [{self.name}] cannot end more than once")
        else:
            if not self._trial.ending:
                self._post_outgoing_data(_Ending())
            packed_obs = self._pack_observations(final_observations, -1)
            self._post_outgoing_data(packed_obs)
            if self._auto_ack:
                self._post_outgoing_data(_EndingAck())

    def _pack_observations(self, observations, tick_id):
        timestamp = int(time.time() * 1e9)

        new_obs = [None] * len(self._trial.actors)

        for target, obs in observations:
            if not isinstance(target, str):
                raise CogmentError(f"Target actor name [{target}] must be a string")

            if target == "*" or target == "*.*":
                if len(observations) > 1:
                    raise CogmentError(f"Duplicate actors in observations list when using a wildcard")
                new_obs = [obs] * len(self._trial.actors)
                break
            else:
                for actor_index, actor in enumerate(self._trial.actors):
                    if "." not in target:
                        if actor.name == target:
                            if new_obs[actor_index] is not None:
                                raise CogmentError(f"Duplicate actor [{actor.name}] in observations list")
                            new_obs[actor_index] = obs
                            break  # Names are unique in trial
                    else:
                        class_name, actor_name = target.split(".")
                        if class_name == actor.actor_class.name:
                            if actor_name == actor.name or actor_name == "*":
                                if new_obs[actor_index] is not None:
                                    raise CogmentError(f"Duplicate actor [{class_name}.{actor.name}] "
                                                       f"in observations list")
                                new_obs[actor_index] = obs

        for actor_index, actor in enumerate(self._trial.actors):
            if new_obs[actor_index] is None:
                raise CogmentError(f"Actor [{actor.name}] is missing an observation")

        package = env_api.ObservationSet()
        package.tick_id = tick_id
        package.timestamp = timestamp

        seen_observations = {}
        for actor_index, actor in enumerate(self._trial.actors):
            actor_obs = new_obs[actor_index]
            obs_id = id(actor_obs)
            obs_key = seen_observations.get(obs_id)
            if obs_key is None:
                obs_key = len(package.observations)

                package.observations.append(actor_obs.SerializeToString())

                seen_observations[obs_id] = obs_key

            package.actors_map.append(obs_key)

        return package

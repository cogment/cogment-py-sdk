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

from cogment.api.common_pb2 import VersionInfo, ObservationData
from cogment.version import __version__
from cogment.delta_encoding import DecodeObservationData

from types import SimpleNamespace

import grpc


def list_versions():
    reply = VersionInfo()
    reply.versions.add(name='cogment_sdk', version=__version__)
    reply.versions.add(name='grpc', version=grpc.__version__)

    return reply


def raw_params_to_user_params(params, settings):
    trial_config = None
    if params.HasField("trial_config"):
        trial_config = settings.trial.config_type()
        trial_config.ParseFromString(params.trial_config.content)

    env_config = None
    if(params.environment.HasField("config")):
        env_config = settings.environment.config_type()
        env_config.ParseFromString(params.environment.config.content)

    environment = SimpleNamespace(
        endpoint=params.environment.endpoint,
        config=env_config
    )

    actors = []

    for a in params.actors:
        actor_config = None

        if a.HasField("config"):
            a_c = settings.actor_classes.__getattribute__(a.actor_class)
            actor_config = a_c.config_type()
            actor_config.ParseFromString(a.config.content)

        actor = SimpleNamespace(
            actor_class=a.actor_class,
            endpoint=a.endpoint,
            config=actor_config
        )

        actors.append(actor)

    return SimpleNamespace(
        trial_config=trial_config,
        environment=environment,
        actors=actors,
        max_steps=params.max_steps,
        max_inactivity=params.max_inactivity
    )


class DecodeData():

    def __init__(self, trial_params, cog_project):
        self.__cog_project = cog_project
        self.last_obs = []

        actor_classes_list = [
            actor.id_ for actor in self.__cog_project.actor_classes]
        trial_actor_list = [actor.actor_class for actor in trial_params.actors]
        self.actor_counts = [0] * len(actor_classes_list)
        for index, actor_class in enumerate(actor_classes_list):
            self.actor_counts[index] += trial_actor_list.count(actor_class)

        for ac_index, actor_class in enumerate(self.__cog_project.actor_classes):
            count = self.actor_counts[ac_index]
            self.last_obs.extend([None] * count)

    def decode_datasample(self, sample):

        actor_id = 0
        for ac_index, actor_class in enumerate(self.__cog_project.actor_classes):
            count = self.actor_counts[ac_index]
            for j in range(count):
                try:
                    obs_id = sample.observations.actors_map[
                        actor_id]
                except Exception:
                    print(sample)

                obs_data = sample.observations.observations[obs_id]

                obs = DecodeObservationData(
                    actor_class, obs_data, self.last_obs[actor_id])
                self.last_obs[actor_id] = obs

                actor_id += 1

        action_list = []
        for act_data in sample.actions:
            action = self.__cog_project.data_pb.Action()
            action.ParseFromString(act_data.content)
            action_list.append(action)

        reward_list = []
        for rwd in sample.rewards:
            reward_list.append((rwd.value, rwd.confidence))

        return self.last_obs, action_list, reward_list

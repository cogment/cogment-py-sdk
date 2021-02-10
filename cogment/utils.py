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

import cogment.api.common_pb2 as common_api
from cogment.version import __version__
from cogment.delta_encoding import DecodeObservationData

import logging
import importlib
import grpc


def list_versions():
    reply = common_api.VersionInfo()
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

    environment = {
        "endpoint": params.environment.endpoint,
        "config": env_config
    }

    actors = []
    for actor in params.actors:
        actor_config = None

        if actor.HasField("config"):
            a_c = settings.actor_classes.__getattribute__(actor.actor_class)
            actor_config = a_c.config_type()
            actor_config.ParseFromString(actor.config.content)

        actor_data = {
            "name": actor.name,
            "actor_class": actor.actor_class,
            "endpoint": actor.endpoint,
            "implementation": actor.implementation,
            "config": actor_config
        }
        actors.append(actor_data)

    return {
        "trial_config": trial_config,
        "environment": environment,
        "actors": actors,
        "max_steps": params.max_steps,
        "max_inactivity": params.max_inactivity
    }


def user_params_to_raw_params(params, settings):
    result = common_api.TrialParams()

    result.max_steps = params["max_steps"]
    result.max_inactivity = params["max_inactivity"]

    if params["trial_config"] is not None:
        result.trial_config.content = params["trial_config"].SerializeToString()

    result.environment.endpoint = params["environment"]["endpoint"]
    if params["environment"]["config"] is not None:
        result.environment.config.content = params["environment"]["config"].SerializeToString()

    for actor_data in params["actors"]:
        actor_pb = result.actors.add()
        actor_pb.name = actor_data["name"]
        actor_pb.actor_class = actor_data["actor_class"]
        actor_pb.endpoint = actor_data["endpoint"]
        actor_pb.implementation = actor_data["implementation"]
        if actor_data["config"] is not None:
            actor_pb.config.content = actor_data["config"].SerializeToString()

    return result


class DecodeData():

    def __init__(self, trial_params, cog_settings):
        self.__cog_settings = cog_settings
        self.last_obs = []

        actor_classes_list = [
            actor.id for actor in self.__cog_settings.actor_classes]
        trial_actor_list = [actor.actor_class for actor in trial_params.actors]
        self.actor_counts = [0] * len(actor_classes_list)
        for index, actor_class in enumerate(actor_classes_list):
            self.actor_counts[index] += trial_actor_list.count(actor_class)

        for ac_index, actor_class in enumerate(self.__cog_settings.actor_classes):
            count = self.actor_counts[ac_index]
            self.last_obs.extend([None] * count)

    def decode_datasample(self, sample):

        actor_index = 0
        for ac_index, actor_class in enumerate(self.__cog_settings.actor_classes):
            count = self.actor_counts[ac_index]
            for _ in range(count):
                obs_id = sample.observations.actors_map[actor_index]
                obs_data = sample.observations.observations[obs_id]

                obs = DecodeObservationData(
                    actor_class, obs_data, self.last_obs[actor_index])
                self.last_obs[actor_index] = obs

                actor_index += 1

        action_list = []
        for act_data in sample.actions:
            action = self.__cog_settings.data_pb.Action()
            action.ParseFromString(act_data.content)
            action_list.append(action)

        reward_list = []
        for rwd in sample.rewards:
            reward_list.append((rwd.value, rwd.confidence))

        message_list = []
        for messages in sample.messages:
            sub_msg_list = []
            for message in messages.messages:

                class_type = message.payload.type_url.split('.')
                user_data = getattr(importlib.import_module(
                    self.__cog_settings.protolib), class_type[-1])()
                message.payload.Unpack(user_data)

                sub_msg_list.append((message.sender_name, user_data))

            message_list.append(sub_msg_list)

        return self.last_obs, action_list, reward_list, message_list

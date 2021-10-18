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
from cogment.version import __version__
from cogment.session import RecvEvent, RecvObservation, RecvMessage, RecvReward

import logging
import importlib
import grpc

# logging level for "trace" (repeated output in critical path)
# Use: logging.log(TRACE, f"This is a trace message for {my_pgm}")
TRACE = 5


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
        "name": params.environment.name,
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
    result.environment.name = params["environment"]["name"]
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

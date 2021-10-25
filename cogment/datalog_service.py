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
import cogment.api.datalog_pb2_grpc as grpc_api
import cogment.api.datalog_pb2 as datalog_api
from cogment.datalog import DatalogSession
from cogment.errors import CogmentError
from cogment.utils import list_versions
import logging
import asyncio

import grpc.aio  # type: ignore


def raw_params_to_logger_params(params, settings):
    trial_config = None
    if params.HasField("trial_config"):
        trial_config = settings.trial.config_type()
        trial_config.ParseFromString(params.trial_config.content)

    env_config = None
    if(params.environment.HasField("config")):
        env_config = settings.environment.config_type()
        env_config.ParseFromString(params.environment.config.content)

    datalog = {
        "endpoint": params.datalog.endpoint,
        "type": params.datalog.type,
        "exclude": params.datalog.exclude_fields
    }

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
        "datalog": datalog,
        "environment": environment,
        "actors": actors,
        "max_steps": params.max_steps,
        "max_inactivity": params.max_inactivity
    }


async def read_sample(context, session):
    try:
        while True:
            request = await context.read()

            if request == grpc.aio.EOF:
                logging.info(f"The orchestrator disconnected from LogExpoterService.")
                break

            elif request.HasField("sample"):
                trial_ended = (request.sample.info.state == common_api.TrialState.ENDED)
                session._new_sample(request.sample)
                if trial_ended:
                    break
            else:
                logging.warning(f"Invalid request received from the orchestrator : {request}")

    except asyncio.CancelledError as exc:
        logging.debug(f"DatalogServicer 'read_sample' coroutine cancelled: [{exc}]")
        raise

    except Exception:
        logging.exception("read_sample")
        raise

    # Exit the loop
    session._new_sample(None)


class DatalogServicer(grpc_api.DatalogSPServicer):
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

            trial_params = raw_params_to_logger_params(request.trial_params, self.__cog_settings)
            raw_trial_params = request.trial_params

            session = DatalogSession(self._impl, trial_id, user_id, trial_params, raw_trial_params)
            user_task = session._start_user_task()

            reader_task = asyncio.create_task(read_sample(context, session))

            # TODO: Investigate probable bug in easy_grpc that expects a stream to be "used"
            reply = datalog_api.RunTrialDatalogOutput()
            await context.write(reply)

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

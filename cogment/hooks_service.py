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
import cogment.api.hooks_pb2_grpc as grpc_api
import cogment.api.hooks_pb2 as hooks_api
from cogment.trial import Trial
from cogment.prehook import PrehookSession
from cogment.errors import CogmentError

import logging
import asyncio


class PrehookServicer(grpc_api.TrialHooksSPServicer):

    def __init__(self, impl, cog_settings, prometheus_registry=None):
        self.__impl = impl
        self.__cog_settings = cog_settings

        logging.info("Prehook Service started")

    # TODO: Check every field's presence and set the resulting session value to None if not present
    def _decode(self, session, proto_params):
        if proto_params.HasField("trial_config"):
            session.trial_config = self.__cog_settings.trial.config_type()
            session.trial_config.ParseFromString(proto_params.trial_config.content)
        else:
            session.trial_config = None

        session.trial_max_steps = proto_params.max_steps
        session.trial_max_inactivity = proto_params.max_inactivity

        session.datalog_endpoint = proto_params.datalog.endpoint
        session.datalog_exclude = [field for field in proto_params.datalog.exclude_fields]

        if proto_params.environment.HasField("config"):
            session.environment_config = self.__cog_settings.environment.config_type()
            session.environment_config.ParseFromString(proto_params.environment.config.content)
        else:
            session.environment_config = None
        session.environment_endpoint = proto_params.environment.endpoint
        session.environment_name = proto_params.environment.name
        session.environment_implementation = proto_params.environment.implementation

        session.actors = []
        for actor in proto_params.actors:
            if actor.HasField("config"):
                a_c = self.__cog_settings.actor_classes.__getattribute__(actor.actor_class)
                actor_config = a_c.config_type()
                actor_config.ParseFromString(actor.config.content)
            else:
                actor_config = None

            actor_data = {
                "name": actor.name,
                "actor_class": actor.actor_class,
                "endpoint": actor.endpoint,
                "implementation": actor.implementation,
                "config": actor_config
            }
            session.actors.append(actor_data)

    # TODO: Take into account if any of the session value is None?
    def _recode(self, session):
        proto_params = common_api.TrialParams()

        if hasattr(session, "trial_config") and session.trial_config is not None:
            proto_params.trial_config.content = session.trial_config.SerializeToString()
        if hasattr(session, "trial_max_steps") and session.trial_max_steps is not None:
            proto_params.max_steps = session.trial_max_steps
        if hasattr(session, "trial_max_inactivity") and session.trial_max_inactivity is not None:
            proto_params.max_inactivity = session.trial_max_inactivity

        if hasattr(session, "datalog_endpoint") and session.datalog_endpoint is not None:
            proto_params.datalog.endpoint = session.datalog_endpoint
        if hasattr(session, "datalog_exclude") and session.datalog_exclude is not None:
            proto_params.datalog.exclude_fields.extend(session.datalog_exclude)

        if hasattr(session, "environment_config") and session.environment_config is not None:
            proto_params.environment.config.content = session.environment_config.SerializeToString()
        if hasattr(session, "environment_endpoint") and session.environment_endpoint is not None:
            proto_params.environment.endpoint = session.environment_endpoint
        if hasattr(session, "environment_name") and session.environment_name is not None:
            proto_params.environment.name = session.environment_name
        if hasattr(session, "environment_implementation") and session.environment_implementation is not None:
            proto_params.environment.implementation = session.environment_implementation

        if hasattr(session, "actors") and session.actors is not None:
            for actor_data in session.actors:
                actor_pb = proto_params.actors.add()
                if "name" in actor_data:
                    actor_pb.name = actor_data["name"]
                if "actor_class" in actor_data:
                    actor_pb.actor_class = actor_data["actor_class"]
                if "endpoint" in actor_data:
                    actor_pb.endpoint = actor_data["endpoint"]
                if "implementation" in actor_data:
                    actor_pb.implementation = actor_data["implementation"]
                if "config" in actor_data and actor_data["config"] is not None:
                    actor_pb.config.content = actor_data["config"].SerializeToString()

        return proto_params

    # Override
    async def OnPreTrial(self, request, context):
        if not self.__impl:
            logging.warning("No implementation registered on prehook request")
            raise CogmentError("No implementation registered")

        try:
            metadata = dict(context.invocation_metadata())
            logging.debug(f"Received metadata: [{metadata}]")
            trial_id = metadata["trial-id"]
            user_id = metadata["user-id"]

            trial = Trial(trial_id, [], self.__cog_settings)

            prehook = PrehookSession(trial, user_id)
            self._decode(prehook, request.params)
            try:
                await self.__impl(prehook)
                prehook.validate()

            except asyncio.CancelledError as exc:
                logging.debug(f"Prehook implementation coroutine cancelled: [{exc}]")
                return False

            except Exception:
                logging.exception(f"An exception occured in user prehook implementation:")
                raise

            reply = hooks_api.PreTrialParams()
            reply.params.CopyFrom(self._recode(prehook))

            return reply

        except Exception:
            logging.exception("OnPreTrial")
            raise

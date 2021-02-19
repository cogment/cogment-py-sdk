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

import grpc
import grpc.experimental.aio

import cogment.api.orchestrator_pb2 as orchestrator_api
from cogment.actor import _ClientActorSession, RecvReward
import cogment.api.orchestrator_pb2_grpc as grpc_api
from cogment.delta_encoding import DecodeObservationData
from cogment.errors import InvalidRequestError
from cogment.trial import Trial
from types import SimpleNamespace

import asyncio
import logging
import traceback


async def read_observations(client_session, reply_itor):
    try:
        async for reply in reply_itor:
            if not reply.final_data:
                for obs_reply in reply.data.observations:
                    tick_id = obs_reply.tick_id
                    client_session._trial.tick_id = tick_id

                    obs = DecodeObservationData(
                        client_session._actor_class,
                        obs_reply.data,
                        client_session._latest_observation)
                    client_session._latest_observation = obs
                    client_session._new_observation(obs)

                for rew_request in reply.data.rewards:
                    reward = RecvReward()
                    reward._set_all(rew_request)
                    client_session._new_reward(reward)

                for message in reply.data.messages:
                    client_session._new_message(message)

            else:
                client_session._trial.over = True

                package = SimpleNamespace(observations=[], rewards=[], messages=[])
                tick_id = None

                for obs_reply in reply.data.observations:
                    tick_id = obs_reply.tick_id
                    obs = DecodeObservationData(
                        client_session._actor_class,
                        obs_reply.data,
                        client_session._latest_observation)
                    client_session._latest_observation = obs
                    package.observations.append(obs)

                for rew_request in reply.data.rewards:
                    reward = RecvReward()
                    reward._set_all(rew_request)
                    package.rewards.append(reward)

                for msg_request in reply.data.messages:
                    package.messages.append(msg_request)

                if tick_id is not None:
                    client_session._trial.tick_id = tick_id

                await client_session._end(package)

                break

    except asyncio.CancelledError:
        logging.debug(f"Client [{client_session.name}] 'read_observations' coroutine cancelled")

    except grpc.experimental.aio._call.AioRpcError as exc:
        if exc.code() == grpc.StatusCode.UNAVAILABLE:
            logging.error(f"Orchestrator communication lost: [{exc.details()}]")
            logging.debug(f"gRPC Error details: [{exc.debug_error_string()}]")
            client_session._task.cancel()
        else:
            raise

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


async def write_actions(client_session):
    try:
        while True:
            act = await client_session._retrieve_action()

            action_req = orchestrator_api.TrialActionRequest()
            if act is not None:
                action_req.action.content = act.SerializeToString()

            yield action_req

    except asyncio.CancelledError:
        logging.debug(f"Client [{client_session.name}] 'write_actions' coroutine cancelled")

    except Exception:
        logging.error(f"{traceback.format_exc()}")
        raise


class ClientServicer:
    def __init__(self, cog_settings, endpoint):
        self.cog_settings = cog_settings

        if endpoint.private_key is None:
            channel = grpc.experimental.aio.insecure_channel(endpoint.url)
        else:
            if endpoint.root_certificates:
                root = bytes(endpoint.root_certificates, "utf-8")
            else:
                root = None
            if endpoint.private_key:
                key = bytes(endpoint.private_key, "utf-8")
            else:
                key = None
            if endpoint.certificate_chain:
                certs = bytes(endpoint.certificate_chain, "utf-8")
            else:
                certs = None
            creds = grpc.ssl_channel_credentials(root, key, certs)
            channel = grpc.experimental.aio.secure_channel(endpoint.url, creds)

        self._actor_stub = grpc_api.ClientActorStub(channel)

    async def run(self, trial_id, impl, impl_name, actor_classes, actor_name):

        # TODO: Handle properly the multiple actor classes.  Including "all" classes
        #       when the list is empty
        if actor_name is None:
            requested_actor_class = actor_classes[0]
            req = orchestrator_api.TrialJoinRequest(trial_id=trial_id, actor_class=requested_actor_class)
        else:
            req = orchestrator_api.TrialJoinRequest(trial_id=trial_id, actor_name=actor_name)

        reply = await self._actor_stub.JoinTrial(req)

        trial = Trial(reply.trial_id, reply.actors_in_trial, self.cog_settings)

        self_info = None
        for info in reply.actors_in_trial:
            if info.name == reply.actor_name:
                self_info = info
                break
        if self_info is None:
            raise InvalidRequestError(
                f"Unknown actor name: [{reply.actor_name}] not found in [{reply.actors_in_trial}]", request=reply)

        actor_class = self.cog_settings.actor_classes[self_info.actor_class]

        config = None
        if reply.HasField("config"):
            if actor_class.config_type is None:
                raise Exception(
                    f"Actor [{self_info.name}] received config data of unknown type (was it defined in cogment.yaml)")
            config = actor_class.config_type()
            config.ParseFromString(reply.config.content)

        new_session = _ClientActorSession(
            impl, actor_class, trial, self_info.name, impl_name, config, self._actor_stub
        )

        metadata = (("trial-id", trial.id), ("actor-name", self_info.name))
        req_itor = write_actions(new_session)
        reply_itor = self._actor_stub.ActionStream(request_iterator=req_itor, metadata=metadata)

        reader_task = asyncio.create_task(read_observations(new_session, reply_itor))

        try:
            new_session._task = asyncio.create_task(new_session._run())
            await new_session._task
            logging.debug(f"User client implementation for [{new_session.name}] returned")

        except Exception:
            logging.error(f"{traceback.format_exc()}")
            raise

        finally:
            reader_task.cancel()

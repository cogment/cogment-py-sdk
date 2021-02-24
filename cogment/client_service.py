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
from cogment.actor import _ClientActorSession
from cogment.session import RecvEvent, RecvObservation, RecvMessage, RecvReward, EventType
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
                event_type = EventType.ACTIVE
            else:
                event_type = EventType.ENDING
                client_session._trial.over = True

            events = {}
            for obs_request in reply.data.observations:
                snapshot = DecodeObservationData(
                    client_session._actor_class,
                    obs_request.data,
                    client_session._latest_observation)
                client_session._latest_observation = snapshot

                evt = events.setdefault(obs_request.tick_id, RecvEvent(event_type))
                if evt.observation:
                    logging.warning(f"Client received two observations with the same tick_id: {obs_request.tick_id}")
                else:
                    evt.observation = RecvObservation(obs_request, snapshot)

            for rew in reply.data.rewards:
                evt = events.setdefault(rew.tick_id, RecvEvent(event_type))
                evt.rewards.append(RecvReward(rew))

            for msg in reply.data.messages:
                evt = events.setdefault(msg.tick_id, RecvEvent(event_type))
                evt.messages.append(RecvMessage(msg))

            ordered_ticks = sorted(events)
            if ordered_ticks:
                client_session._trial.tick_id = ordered_ticks[-1]

            if not reply.final_data:
                for tick_id in ordered_ticks:
                    client_session._new_event(events[tick_id])
            else:
                evt = RecvEvent(EventType.FINAL)
                for tick_id in ordered_ticks:
                    evt = events.pop(tick_id)
                    if events:  # Last event is handled after the loop
                        client_session._new_event(evt)

                evt.type = EventType.FINAL
                client_session._new_event(evt)
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
            impl, actor_class, trial, self_info.name, impl_name, config, self._actor_stub)

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

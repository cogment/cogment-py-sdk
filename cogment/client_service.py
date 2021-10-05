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

import grpc
import grpc.aio  # type: ignore

import cogment.api.common_pb2 as common_api
import cogment.api.orchestrator_pb2_grpc as grpc_api

from cogment.actor import ActorSession
from cogment.utils import TRACE
from cogment.errors import CogmentError
from cogment.session import RecvEvent, RecvObservation, RecvMessage, RecvReward, EventType, _EndingAck
from cogment.delta_encoding import DecodeObservationData
from cogment.trial import Trial

import asyncio
import logging


class _EndQueue:
    pass


def _process_normal_data(data, session):
    if session._trial.ending:
        recv_event = RecvEvent(EventType.ENDING)
    else:
        recv_event = RecvEvent(EventType.ACTIVE)

    if data.HasField("observation"):
        logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}] received an observation")

        if session._trial.ending and session._auto_ack:
            session._post_data(_EndingAck())

        session._trial.tick_id = data.observation.tick_id

        snapshot = DecodeObservationData(
            session._actor_class,
            data.observation.data,
            session._latest_observation,
        )
        session._latest_observation = snapshot

        recv_event.observation = RecvObservation(data.observation, snapshot)
        session._new_event(recv_event)

    elif data.HasField("reward"):
        logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}] received reward")

        recv_event.rewards = [RecvReward(data.reward)]
        session._new_event(recv_event)

    elif data.HasField("message"):
        logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}] received message")

        recv_event.messages = [RecvMessage(data.message)]
        session._new_event(recv_event)

    elif data.HasField("details"):
        logging.warning(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                        f"received unexpected detail data [{data.details}]")

    else:
        logging.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                      f"received unexpected data [{data.WhichOneof('data')}]")


async def _process_incoming(reply_itor, req_queue, session):
    try:
        async for data in reply_itor:
            if data == grpc.aio.EOF:
                logging.info(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                             f"The orchestrator disconnected the actor")
                break
            logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                               f"Received data [{data.state}] [{data.WhichOneof('data')}]")

            if data.state == common_api.CommunicationState.NORMAL:
                _process_normal_data(data, session)

            elif data.state == common_api.CommunicationState.HEARTBEAT:
                logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}] "
                                   f"received 'HEARTBEAT' and responding in kind")
                reply = common_api.ActorRunTrialOutput()
                reply.state = data.state
                await req_queue.put(reply)

            elif data.state == common_api.CommunicationState.LAST:
                logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] received 'LAST' state")
                session._trial.ending = True

            elif data.state == common_api.CommunicationState.LAST_ACK:
                logging.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                              f"received an unexpected 'LAST_ACK'")
                # TODO: Should we `return` or raise instead of continuing?

            elif data.state == common_api.CommunicationState.END:
                if session._trial.ending:
                    if data.HasField("details"):
                        logging.info(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                                     f"Trial ended with explanation [{data.details}]")
                    else:
                        logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}]: Trial ended")
                    session._new_event(RecvEvent(EventType.FINAL))
                else:
                    if data.HasField("details"):
                        details = data.details
                    else:
                        details = ""
                    logging.warning(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                                    f"Trial ended forcefully [{details}]")

                session._trial.ended = True
                session._exit_queues()
                break

            else:
                logging.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                              f"received an invalid state [{data.state}]")

    except asyncio.CancelledError as exc:
        logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] coroutine cancelled: [{exc}]")

    except grpc.aio.AioRpcError as exc:
        logging.debug(f"gRPC Error details: [{exc.debug_error_string()}]")
        if exc.code() == grpc.StatusCode.UNAVAILABLE:
            logging.error(f"Orchestrator communication lost: [{exc.details()}]")
            session._exit_queues()
        else:
            logging.exception("_process_incoming -- Unexpected aio error")
            raise

    except Exception:
        logging.exception("_process_incoming")
        raise


async def _process_outgoing(data_queue, session):
    try:
        async for data in session._retrieve_data():
            package = common_api.ActorRunTrialOutput()
            package.state = common_api.CommunicationState.NORMAL

            # Using strict comparison: there is no reason to receive derived classes here
            if type(data) == common_api.Action:
                logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending action")
                package.action.CopyFrom(data)

            elif type(data) == common_api.Reward:
                logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending reward")
                package.reward.CopyFrom(data)

            elif type(data) == common_api.Message:
                logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending message")
                package.message.CopyFrom(data)

            elif type(data) == _EndingAck:
                package.state = common_api.CommunicationState.LAST_ACK
                logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                              f"Sending 'LAST_ACK'")
                await data_queue.put(package)
                break

            else:
                logging.error(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                              f"Unknown data type to send [{type(data)}]")
                continue

            await data_queue.put(package)

    except Exception:
        logging.exception("_process_outgoing")
        raise


class GrpcWriter:
    def __init__(self, data_queue):
        self._queue = data_queue

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            data = await self._queue.get()
            self._queue.task_done()
            if (type(data) != _EndQueue):
                return data

        except asyncio.CancelledError as exc:
            logging.debug(f"Client 'GrpcWriter' coroutine cancelled: [{exc}]")

        except GeneratorExit:
            raise

        except Exception:
            logging.exception("GrpcWriter::anext")
            raise

        raise StopAsyncIteration


class ClientServicer:
    def __init__(self, cog_settings, endpoint):
        self.cog_settings = cog_settings
        self.trial_id = None
        self._request_queue = None
        self._reply_itor = None

        if endpoint.private_key is None:
            channel = grpc.aio.insecure_channel(endpoint.url)
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
            channel = grpc.aio.secure_channel(endpoint.url, creds)

        self._actor_stub = grpc_api.ClientActorSPStub(channel)

    async def join(self, trial_id, actor_name, actor_class):
        if self._request_queue is not None:
            raise CogmentError(f"ClientServicer has already joined")

        req = common_api.ActorRunTrialOutput()
        req.state = common_api.CommunicationState.NORMAL

        init = common_api.ActorInitialOutput()
        if actor_name is not None:
            init.actor_name = actor_name
        elif actor_class is not None:
            init.actor_class = actor_class
        else:
            raise CogmentError(f"Only actor_name or actor_class must be specified, not both.")
        req.init_output.CopyFrom(init)

        self._request_queue = asyncio.Queue()
        await self._request_queue.put(req)

        self.trial_id = trial_id

        req_itor = GrpcWriter(self._request_queue)
        metadata = (("trial-id", trial_id),)
        self._reply_itor = self._actor_stub.RunTrial(request_iterator=req_itor, metadata=metadata)
        if not self._reply_itor:
            raise CogmentError(f"Failed to connect to join trial")

        # TODO: Move out into its own `get_init_data` function
        try:
            async for reply in self._reply_itor:
                logging.debug(f"Trial [{trial_id}] - Received a reply while joining "
                              f"[{reply.state}] [{reply.WhichOneof('data')}]")

                if reply.state == common_api.CommunicationState.NORMAL:
                    if reply.HasField("init_input"):
                        return reply.init_input
                    elif reply.HasField("details"):
                        logging.warning(f"Trial [{trial_id}] - Received unexpected detail data "
                                        f"[{reply.details}] while joining")
                    else:
                        raise CogmentError(f"Unexpected data [{reply.WhichOneof('data')}] while joining")

                elif reply.state == common_api.CommunicationState.HEARTBEAT:
                    reply = common_api.ActorRunTrialOutput()
                    reply.state = reply.state
                    await self._request_queue.put(reply)

                elif reply.state == common_api.CommunicationState.LAST:
                    logging.warning(f"Trial [{trial_id}] - Received 'LAST' state while joining")
                    reply = common_api.ActorRunTrialOutput()
                    reply.state == common_api.CommunicationState.LAST_ACK
                    await self._request_queue.put(reply)
                    break

                elif reply.state == common_api.CommunicationState.LAST_ACK:
                    raise CogmentError(f"Trial [{trial_id}] - Received an unexpected 'LAST_ACK' while joining")

                elif reply.state == common_api.CommunicationState.END:
                    if reply.HasField("details"):
                        details = reply.details
                    else:
                        details = ""
                    logging.warning(f"Trial [{trial_id}] - Ended forcefully [{details}] while joining")
                    break

                else:
                    raise CogmentError(f"Received an invalid state [{reply.state}] while joining")

        except CogmentError:
            raise

        except asyncio.CancelledError as exc:
            logging.debug(f"Trial [{trial_id}] - Join coroutine cancelled: [{exc}]")

        except grpc.aio.AioRpcError as exc:
            logging.debug(f"gRPC Error details: [{exc.debug_error_string()}]")
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                logging.error(f"Orchestrator communication lost: [{exc.details()}]")
            else:
                logging.exception("join -- Unexpected aio error")
                raise

        except Exception:
            logging.exception("join")
            raise

        return None

    async def run_session(self, impl, init_data):
        if self._request_queue is None:
            raise CogmentError(f"ClientServicer has not joined")

        send_task = None
        process_task = None

        trial = Trial(self.trial_id, [], self.cog_settings)
        actor_class = self.cog_settings.actor_classes[init_data.actor_class]

        config = None
        if init_data.HasField("config"):
            if actor_class.config_type is None:
                raise CogmentError(f"Actor [{init_data.actor_name}] received config data of unknown type "
                                    "(was it defined in cogment.yaml)")
            config = actor_class.config_type()
            config.ParseFromString(init_data.config.content)

        session = ActorSession(impl, actor_class, trial, init_data.actor_name, init_data.impl_name, config)
        logging.debug(f"Trial [{self.trial_id}] - impl [{init_data.impl_name}] "
                      f"for client actor [{init_data.actor_name}] started")

        try:
            send_task = asyncio.create_task(_process_outgoing(self._request_queue, session))
            process_task = asyncio.create_task(_process_incoming(self._reply_itor, self._request_queue, session))
            user_task = session._start_user_task()

            logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] session started")
            normal_return = await user_task

            if normal_return:
                if not session._last_event_delivered:
                    logging.warning(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                                    f"user implementation returned before required")
                else:
                    logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                                f"user implementation returned")
            else:
                logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                            f"user implementation was cancelled")

        except asyncio.CancelledError as exc:
            logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                          f"user implementation was cancelled")

        except Exception:
            logging.exception("run_session")
            raise

        finally:
            if self._request_queue is not None:
                await self._request_queue.put(_EndQueue())
            if send_task is not None:
                send_task.cancel()
            if process_task is not None:
                process_task.cancel()

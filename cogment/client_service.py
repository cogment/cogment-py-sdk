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

from cogment.actor import ActorSession
from cogment.utils import logger, INIT_TIMEOUT
from cogment.errors import CogmentError
from cogment.session import RecvEvent, RecvObservation, RecvMessage, RecvReward, EventType, _InitAck, _EndingAck
from cogment.trial import Trial

import asyncio


class _EndQueue:
    """Internal class signaling the end of data queueing."""
    pass


def _impl_can_serve_actor_class(impl, actor_class):
    if impl.actor_classes:
        for ac in impl.actor_classes:
            if ac == actor_class.name:
                return True
        return False
    else:
        return True


def _process_normal_data(data, session):
    if session._trial.ending:
        recv_event = RecvEvent(EventType.ENDING)
    else:
        recv_event = RecvEvent(EventType.ACTIVE)

    if data.HasField("observation"):
        logger.trace(f"Trial [{session._trial.id}] - Actor [{session.name}] received an observation")

        if session._trial.ending and session._auto_ack:
            session._post_outgoing_data(_EndingAck())

        tick_id = data.observation.tick_id
        session._trial.tick_id = tick_id

        obs_space = session._actor_class.observation_space()
        obs_space.ParseFromString(data.observation.content)

        recv_event.observation = RecvObservation(data.observation, obs_space)
        session._post_incoming_event((tick_id, recv_event))

    elif data.HasField("reward"):
        logger.trace(f"Trial [{session._trial.id}] - Actor [{session.name}] received reward")

        recv_event.rewards = [RecvReward(data.reward)]
        session._post_incoming_event((-1, recv_event))

    elif data.HasField("message"):
        logger.trace(f"Trial [{session._trial.id}] - Actor [{session.name}] received message")

        recv_event.messages = [RecvMessage(data.message)]
        session._post_incoming_event((-1, recv_event))

    elif data.HasField("details"):
        logger.warning(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                       f"received unexpected detail data [{data.details}]")

    else:
        logger.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                     f"received unexpected data [{data.WhichOneof('data')}]")


async def _process_incoming(reply_itor, req_queue, session):
    try:
        async for data in reply_itor:
            if data == grpc.aio.EOF:
                logger.info(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                            f"The orchestrator disconnected the actor")
                break
            logger.trace(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                         f"Received data [{data.state}] [{data.WhichOneof('data')}]")

            if data.state == common_api.CommunicationState.NORMAL:
                _process_normal_data(data, session)

            elif data.state == common_api.CommunicationState.HEARTBEAT:
                logger.trace(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                             f"received 'HEARTBEAT' and responding in kind")
                reply = common_api.ActorRunTrialOutput()
                reply.state = data.state
                await req_queue.put(reply)

            elif data.state == common_api.CommunicationState.LAST:
                logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] received 'LAST' state")
                session._trial.ending = True

            elif data.state == common_api.CommunicationState.LAST_ACK:
                logger.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                             f"received an unexpected 'LAST_ACK'")
                # TODO: Should we `return` or raise instead of continuing?

            elif data.state == common_api.CommunicationState.END:
                if session._trial.ending:
                    if data.HasField("details"):
                        logger.info(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                                    f"Trial ended with explanation [{data.details}]")
                    else:
                        logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}]: Trial ended")
                    session._post_incoming_event((-1, RecvEvent(EventType.FINAL)))
                else:
                    if data.HasField("details"):
                        details = data.details
                    else:
                        details = ""
                    logger.warning(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                                   f"Trial ended forcefully [{details}]")

                session._trial.ended = True
                session._exit_queues()
                break

            else:
                logger.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                             f"received an invalid state [{data.state}]")

    except asyncio.CancelledError as exc:
        logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] coroutine cancelled: [{exc}]")
        raise

    except grpc.aio.AioRpcError as exc:
        logger.debug(f"gRPC failed status details: [{exc.debug_error_string()}]")
        if exc.code() == grpc.StatusCode.UNAVAILABLE:
            logger.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                         f"Orchestrator communication lost [{exc.details()}]")
            session._exit_queues()
        else:
            logger.exception("_process_incoming -- Unexpected aio failure")
            raise

    except Exception:
        logger.exception("_process_incoming")
        raise


async def _process_outgoing(data_queue, session):
    try:
        async for data in session._retrieve_outgoing_data():
            package = common_api.ActorRunTrialOutput()
            package.state = common_api.CommunicationState.NORMAL

            # Using strict comparison: there is no reason to receive derived classes here
            if type(data) == common_api.Action:
                logger.trace(f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending action")
                package.action.CopyFrom(data)

            elif type(data) == common_api.Reward:
                logger.trace(f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending reward")
                package.reward.CopyFrom(data)

            elif type(data) == common_api.Message:
                logger.trace(f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending message")
                package.message.CopyFrom(data)

            elif type(data) == _InitAck:
                # The init output was done before we could get here
                continue

            elif type(data) == _EndingAck:
                package.state = common_api.CommunicationState.LAST_ACK
                logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending 'LAST_ACK'")
                await data_queue.put(package)
                break

            else:
                logger.error(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                             f"Unknown data type to send [{type(data)}]")
                continue

            await data_queue.put(package)

    except asyncio.CancelledError as exc:
        logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] process outgoing cancelled: [{exc}]")
        raise

    except Exception:
        logger.exception("_process_outgoing")
        raise


class _GrpcWriter:
    """Internal class encapsulating an async queue to serve as a grpc writing iterator."""

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
            logger.debug(f"Client '_GrpcWriter' coroutine cancelled: [{exc}]")

        except GeneratorExit:
            raise

        except Exception:
            logger.exception("_GrpcWriter::anext")
            raise

        raise StopAsyncIteration


class ClientServicer:
    """Internal client actor servicer class."""

    def __init__(self, cog_settings, stub):
        self.trial_id = None
        self._cog_settings = cog_settings
        self._request_queue = None
        self._reply_itor = None
        self._actor_stub = stub

    async def _get_init_data(self):
        logger.debug(f"Trial [{self.trial_id}] - Processing init for client actor")

        last_received = False
        async for reply in self._reply_itor:
            logger.debug(f"Trial [{self.trial_id}] - Read initial reply: {reply}")

            if reply == grpc.aio.EOF:
                logger.info(f"Trial [{self.trial_id}] - Orchestrator disconnected client actor before start")
                return None

            if reply.state == common_api.CommunicationState.NORMAL:
                if last_received:
                    raise CogmentError(f"Trial [{self.trial_id}] - Received init data after 'LAST'")

                if reply.HasField("init_input"):
                    return reply.init_input
                elif reply.HasField("details"):
                    logger.warning(f"Trial [{self.trial_id}] - Received unexpected detail data "
                                   f"[{reply.details}] before start")
                else:
                    data_set = reply.WhichOneof("data")
                    raise CogmentError(f"Trial [{self.trial_id}] - Received unexpected init data [{data_set}]")

            elif reply.state == common_api.CommunicationState.HEARTBEAT:
                req = common_api.ActorRunTrialOutput()
                req.state = reply.state
                await self._request_queue.put(req)

            elif reply.state == common_api.CommunicationState.LAST:
                if last_received:
                    raise CogmentError(f"Trial [{self.trial_id}] - Before start, received unexpected 'LAST' "
                                       f"when waiting for 'END'")

                logger.debug(f"Trial [{self.trial_id}] - Ending before init data")
                req = common_api.ActorRunTrialOutput()
                req.state = common_api.CommunicationState.LAST_ACK
                await self._request_queue.put(req)
                last_received = True

            elif reply.state == common_api.CommunicationState.LAST_ACK:
                raise CogmentError(f"Trial [{self.trial_id}] - Before start, received an unexpected 'LAST_ACK'")

            elif reply.state == common_api.CommunicationState.END:
                if reply.HasField("details"):
                    logger.info(f"Trial [{self.trial_id}] - Ended before start [{reply.details}]")
                else:
                    logger.debug(f"Trial [{self.trial_id}] - Ended before start")
                return None

            else:
                raise CogmentError(f"Trial [{self.trial_id}] - Before start, received an invalid state "
                                   f"[{reply.state}] [{reply}]")

    def _start_session(self, impl, init_data):
        actor_name = init_data.actor_name
        if not actor_name:
            raise CogmentError(f"Trial [{self.trial_id}] - Empty actor name for client actor")

        actor_class = self._cog_settings.actor_classes.get(init_data.actor_class)
        if actor_class is None:
            raise CogmentError(f"Trial [{self.trial_id}] - "
                               f"Unknown class [{init_data.actor_class}] for client actor [{actor_name}]")

        config = None
        if init_data.HasField("config"):
            if actor_class.config_type is None:
                raise CogmentError(f"Trial [{self.trial_id}] - Client actor [{actor_name}] "
                                   f"received config data of unknown type (was it defined in cogment.yaml?)")
            config = actor_class.config_type()
            config.ParseFromString(init_data.config.content)

        trial = Trial(self.trial_id, [], self._cog_settings)
        new_session = ActorSession(impl, actor_class, trial, actor_name, init_data.impl_name,
                                   init_data.env_name, config)

        logger.debug(f"Trial [{self.trial_id}] - impl [{init_data.impl_name}] for actor [{actor_name}] started")

        return new_session

    async def run_session(self, impl, init_data):
        if self._request_queue is None:
            raise CogmentError(f"ClientServicer has not joined")

        send_task = None
        process_task = None

        session = self._start_session(impl, init_data)

        try:
            send_task = asyncio.create_task(_process_outgoing(self._request_queue, session))
            process_task = asyncio.create_task(_process_incoming(self._reply_itor, self._request_queue, session))
            user_task = session._start_user_task()

            logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] session started")
            normal_return = await user_task

            if normal_return:
                if not session._last_event_delivered:
                    logger.warning(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                                   f"user implementation returned before required")
                else:
                    logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                                 f"user implementation returned")
            else:
                logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                             f"user implementation was cancelled")

        except asyncio.CancelledError as exc:
            logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                         f"user implementation was cancelled")

        except Exception:
            logger.exception("run_session")
            raise

        finally:
            if self._request_queue is not None:
                await self._request_queue.put(_EndQueue())
            if send_task is not None:
                send_task.cancel()
            if process_task is not None:
                process_task.cancel()

    async def join_trial(self, trial_id, actor_name, actor_class):
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

        req_itor = _GrpcWriter(self._request_queue)
        metadata = (("trial-id", trial_id),)
        self._reply_itor = self._actor_stub.RunTrial(request_iterator=req_itor, metadata=metadata)
        if not self._reply_itor:
            raise CogmentError(f"Failed to connect to join trial")

        try:
            return await asyncio.wait_for(self._get_init_data(), INIT_TIMEOUT)

        except CogmentError:
            raise

        except asyncio.TimeoutError:
            logger.error(f"Trial [{trial_id}] - Join failed to receive init data from Orchestrator")

        except asyncio.CancelledError as exc:
            logger.error(f"Trial [{trial_id}] - Join coroutine cancelled before start: [{exc}]")

        except grpc.aio.AioRpcError as exc:
            logger.debug(f"gRPC failed status details: [{exc.debug_error_string()}]")
            if exc.code() == grpc.StatusCode.UNAVAILABLE:
                logger.error(f"Trial [{trial_id}] - Actor [{actor_name}] "
                             f"Orchestrator communication lost in init [{exc.details()}]")
            else:
                logger.exception("join_trial -- Unexpected aio failure")
                raise

        except Exception:
            logger.exception("join_trial")
            raise

        return None

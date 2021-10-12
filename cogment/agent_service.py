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

import cogment.api.agent_pb2_grpc as grpc_api
import cogment.api.agent_pb2 as agent_api
import cogment.api.common_pb2 as common_api

from cogment.utils import list_versions, TRACE
from cogment.trial import Trial

from cogment.actor import ActorSession
from cogment.session import RecvEvent, RecvObservation, RecvMessage, RecvReward, EventType, _EndingAck
from cogment.errors import CogmentError

from prometheus_client import Summary, Counter, Gauge

from types import SimpleNamespace
import atexit
import logging
import asyncio
import grpc  # type: ignore
import grpc.aio  # type: ignore


class _PrometheusData:
    def __init__(self, prometheus_registry):
        self.decide_request_time = Summary(
            "actor_decide_processing_seconds",
            "Time spent by an actor on the decide function",
            ["name", "impl_name"],
            registry=prometheus_registry)
        self.actors_started = Counter(
            "actor_started", "Number of actors created", ["impl_name"],
            registry=prometheus_registry)
        self.actors_ended = Counter(
            "actor_ended", "Number of actors ended", ["impl_name"],
            registry=prometheus_registry)
        self.messages_received = Counter(
            "actor_received_messages", "Number of messages received", ["name", "impl_name"],
            registry=prometheus_registry)
        self.rewards_received = Gauge(
            "actor_reward_summation", "Cumulative rewards received", ["name", "impl_name"],
            registry=prometheus_registry)
        self.rewards_counter = Counter(
            "actor_rewards_count", "Number of rewards received", ["name", "impl_name"],
            registry=prometheus_registry)


def _trial_key(trial_id, actor_name):
    return f"{trial_id}_{actor_name}"


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
        logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}] received an observation")

        if session._trial.ending and session._auto_ack:
            session._post_data(_EndingAck())

        session._trial.tick_id = data.observation.tick_id

        obs_space = session._actor_class.observation_space()
        obs_space.ParseFromString(data.observation.content)

        recv_event.observation = RecvObservation(data.observation, obs_space)
        session._new_event(recv_event)

    elif data.HasField("reward"):
        logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}] received reward")

        recv_event.rewards = [RecvReward(data.reward)]
        session._new_event(recv_event)

        value = recv_event.rewards[0].value
        session._prometheus_data.rewards_counter.labels(session.name, session.impl_name).inc()
        if value < 0.0:
            session._prometheus_data.rewards_received.labels(session.name, session.impl_name).dec(abs(value))
        else:
            session._prometheus_data.rewards_received.labels(session.name, session.impl_name).inc(value)

    elif data.HasField("message"):
        logging.log(TRACE, f"Trial [{session._trial.id}] - Actor [{session.name}] received message")

        recv_event.messages = [RecvMessage(data.message)]
        session._new_event(recv_event)

        session._prometheus_data.messages_received.labels(session.name, session.impl_name).inc()

    elif data.HasField("details"):
        logging.warning(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                        f"received unexpected detail data [{data.details}]")

    else:
        logging.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                      f"received unexpected data [{data.WhichOneof('data')}]")


async def _process_incoming(context, session):
    try:
        session._prometheus_data.actors_started.labels(session.impl_name).inc()

        while True:
            data = await context.read()
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
                await context.write(reply)

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

                session._prometheus_data.actors_ended.labels(session.impl_name).inc()
                break

            else:
                logging.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                              f"received an invalid state [{data.state}]")

    except asyncio.CancelledError as exc:
        logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] coroutine cancelled: [{exc}]")

    except Exception:
        logging.exception("_process_incoming")
        raise


async def _process_outgoing(context, session):
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
                logging.debug(f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending 'LAST_ACK'")
                await context.write(package)
                break

            else:
                logging.error(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                              f"Unknown data type to send [{type(data)}]")
                continue

            await context.write(package)

    except Exception:
        logging.exception("_process_outgoing")
        raise


class AgentServicer(grpc_api.ServiceActorSPServicer):
    def __init__(self, agent_impls, cog_settings, prometheus_registry=None):
        self.__impls = agent_impls
        self._sessions = set()
        self.__cog_settings = cog_settings
        self._prometheus_data = _PrometheusData(prometheus_registry)

        logging.info("Agent Service started")

    def _start_session(self, trial_id, init_input):
        actor_name = init_input.actor_name
        if not actor_name:
            raise CogmentError(f"Trial [{trial_id}] - Empty actor name for service actor")

        if init_input.impl_name:
            impl_name = init_input.impl_name
            impl = self.__impls.get(impl_name)
            if impl is None:
                raise CogmentError(f"Trial [{trial_id}] - "
                                   f"Unknown impl [{impl_name}] for service actor [{actor_name}]")
        else:
            impl_name, impl = next(iter(self.__impls.items()))
            logging.info(f"Trial [{trial_id}] - "
                         f"impl [{impl_name}] arbitrarily chosen for service actor [{actor_name}]")

        if init_input.actor_class not in self.__cog_settings.actor_classes:
            raise CogmentError(f"Trial [{trial_id}] - "
                               f"Unknown class [{init_input.actor_class}] for service actor [{actor_name}]")
        actor_class = self.__cog_settings.actor_classes[init_input.actor_class]

        if not _impl_can_serve_actor_class(impl, actor_class):
            raise CogmentError(f"Trial [{trial_id}] - Service actor [{actor_name}]: "
                               f"[{impl}] does not implement actor class [{init_input.actor_class}]")

        key = _trial_key(trial_id, actor_name)
        if key in self._sessions:
            raise CogmentError(f"Trial [{trial_id}] - Service actor [{actor_name}] already exists")

        config = None
        if init_input.HasField("config"):
            if actor_class.config_type is None:
                raise CogmentError(f"Trial [{trial_id}] - Service actor [{actor_name}] "
                                   f"received config data of unknown type (was it defined in cogment.yaml?)")
            config = actor_class.config_type()
            config.ParseFromString(init_input.config.content)

        trial = Trial(trial_id, [], self.__cog_settings)
        new_session = ActorSession(impl.impl, actor_class, trial, actor_name, impl_name, config)
        new_session._prometheus_data = self._prometheus_data
        self._sessions.add(key)

        logging.debug(f"Trial [{trial_id}] - impl [{impl_name}] for service actor [{actor_name}] started")

        return new_session

    async def _run_session(self, context, session):
        send_task = None
        process_task = None

        try:
            with self._prometheus_data.decide_request_time.labels(session.name, session.impl_name).time():
                send_task = asyncio.create_task(_process_outgoing(context, session))
                process_task = asyncio.create_task(_process_incoming(context, session))
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
            if send_task is not None:
                send_task.cancel()
            if process_task is not None:
                process_task.cancel()

    async def _get_init_data(self, context, trial_id):
        logging.debug(f"Trial [{trial_id}] - Processing init for service actor")

        last_received = False
        while True:
            # TODO: Limit the time to wait for init data
            request = await context.read()
            logging.debug(f"Trial [{trial_id}] - Read initial request: {request}")

            if request == grpc.aio.EOF:
                logging.info(f"Trial [{trial_id}] - Orchestrator disconnected service actor before start")
                return None

            if request.state == common_api.CommunicationState.NORMAL:
                if last_received:
                    error_str = (f"Trial [{trial_id}] - Received init data after 'LAST'")
                    logging.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

                if request.HasField("init_input"):
                    return request.init_input
                else:
                    data_set = request.WhichOneof("data")
                    error_str = (f"Trial [{trial_id}] - Received unexpected init data [{data_set}]")
                    logging.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

            elif request.state == common_api.CommunicationState.HEARTBEAT:
                reply = common_api.ActorRunTrialOutput()
                reply.state = request.state
                await context.write(reply)

            elif request.state == common_api.CommunicationState.LAST:
                if last_received:
                    error_str = (f"Trial [{trial_id}] - Before start, received unexpected 'LAST' "
                                    f"when waiting for 'END'")
                    logging.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

                logging.debug(f"Trial [{trial_id}] - Ending before init data")
                reply = common_api.ActorRunTrialOutput()
                reply.state = common_api.CommunicationState.LAST_ACK
                await context.write(reply)
                last_received = True

            elif request.state == common_api.CommunicationState.LAST_ACK:
                error_str = (f"Trial [{trial_id}] - Before start, received an unexpected 'LAST_ACK'")
                logging.error(error_str)
                await context.abort(grpc.StatusCode.UNKNOWN, error_str)

            elif request.state == common_api.CommunicationState.END:
                if request.HasField("details"):
                    logging.info(f"Trial [{trial_id}] - Ended before start [{request.details}]")
                else:
                    logging.debug(f"Trial [{trial_id}] - Ended before start")
                return None

            else:
                error_str = (f"Trial [{trial_id}] - Before start, received an invalid state "
                                f"[{request.state}] [{request}]")
                logging.error(error_str)
                await context.abort(grpc.StatusCode.UNKNOWN, error_str)

    # Override
    async def RunTrial(self, request_iterator, context):
        if len(self.__impls) == 0:
            logging.warning("No implementation registered on trial run request")
            raise CogmentError("No implementation registered")

        metadata = dict(context.invocation_metadata())
        trial_id = metadata["trial-id"]

        try:
            init_data = await self._get_init_data(context, trial_id)
            if init_data is None:
                return
            key = _trial_key(trial_id, init_data.actor_name)

            session = self._start_session(trial_id, init_data)

            init_msg = common_api.ActorRunTrialOutput()
            init_msg.state = common_api.CommunicationState.NORMAL
            init_msg.init_output.SetInParent()
            await context.write(init_msg)

            await self._run_session(context, session)  # Blocking

            self._sessions.remove(key)
            return

        except grpc._cython.cygrpc.AbortError:  # Exception from context.abort()
            raise

        except Exception:
            logging.exception("RunTrial")
            raise

    # Override
    async def Version(self, request, context):
        try:
            return list_versions()

        except Exception:
            logging.exception("Version")
            raise

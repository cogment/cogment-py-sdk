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

import grpc  # type: ignore
import grpc.aio  # type: ignore
from prometheus_client import Summary, Counter, Gauge

import cogment.api.agent_pb2_grpc as agent_grpc_api
import cogment.api.common_pb2 as common_api

from cogment.utils import list_versions, logger, INIT_TIMEOUT
from cogment.trial import Trial
from cogment.actor import ActorSession
from cogment.session import RecvEvent, RecvObservation, RecvMessage, RecvReward, EventType, _InitAck, _EndingAck
from cogment.errors import CogmentError

import asyncio


class _PrometheusData:
    """Internal class holding the details of Prometheus report values for a service actor."""

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


def get_actor_impl(trial_id, actor_impls, init_data):
    if not init_data.actor_name:
        raise CogmentError(f"Trial [{trial_id}] - Empty actor name")
    if not init_data.actor_class:
        raise CogmentError(f"Trial [{trial_id}] - Empty actor class for actor [{init_data.actor_name}]")

    actor_impl = actor_impls.get(init_data.impl_name)
    if actor_impl is not None:
        # Check compatibility
        compatible = (len(actor_impl.actor_classes) == 0)
        for class_name in actor_impl.actor_classes:
            if class_name == init_data.actor_class:
                compatible = True
                break
        if not compatible:
            raise CogmentError(f"Trial [{trial_id}] - actor [{init_data.actor_name}] class [{init_data.actor_class}] "
                               f"is not compatible with actor implementation [{init_data.impl_name}]")
    else:
        # Find a compatible actor class in the registered actors

        # Search for exact match first
        for init_data.impl_name, impl in actor_impls.items():
            for class_name in impl.actor_classes:
                if class_name == init_data.actor_class:
                    actor_impl = impl
                    break
            if actor_impl is not None:
                break

        if actor_impl is None:
            raise CogmentError(f"Trial [{trial_id}] - actor [{init_data.actor_name}] class [{init_data.actor_class}] "
                               f"is not compatible with with any registered actor")

        logger.info(f"Trial [{trial_id}] - "
                    f"impl [{init_data.impl_name}] arbitrarily chosen for actor [{init_data.actor_name}]")

    return actor_impl


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

        value = recv_event.rewards[0].value
        session._prometheus_data.rewards_counter.labels(session.name, session.impl_name).inc()
        if value < 0.0:
            session._prometheus_data.rewards_received.labels(session.name, session.impl_name).dec(abs(value))
        else:
            session._prometheus_data.rewards_received.labels(session.name, session.impl_name).inc(value)

    elif data.HasField("message"):
        logger.trace(f"Trial [{session._trial.id}] - Actor [{session.name}] received message")

        recv_event.messages = [RecvMessage(data.message)]
        session._post_incoming_event((-1, recv_event))

        session._prometheus_data.messages_received.labels(session.name, session.impl_name).inc()

    elif data.HasField("details"):
        logger.warning(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                       f"received unexpected detail data [{data.details}]")

    else:
        logger.error(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                     f"received unexpected data [{data.WhichOneof('data')}]")


async def _process_incoming(context, session):
    try:
        while True:
            data = await context.read()
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
                await context.write(reply)

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

    except Exception:
        logger.exception("_process_incoming")
        raise


async def _process_outgoing(context, session):
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
                package.init_output.SetInParent()
                logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending Init Data")

            elif type(data) == _EndingAck:
                package.state = common_api.CommunicationState.LAST_ACK
                logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}]: Sending 'LAST_ACK'")
                await context.write(package)
                break

            else:
                logger.error(f"Trial [{session._trial.id}] - Actor [{session.name}]: "
                             f"Unknown data type to send [{type(data)}]")
                continue

            await context.write(package)

    except asyncio.CancelledError as exc:
        logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] process outgoing cancelled: [{exc}]")
        raise

    except Exception:
        logger.exception("_process_outgoing")
        raise


class AgentServicer(agent_grpc_api.ServiceActorSPServicer):
    """Internal service actor servicer class."""

    def __init__(self, agent_impls, cog_settings, prometheus_registry=None):
        self._impls = agent_impls
        self._sessions = set()
        self._cog_settings = cog_settings
        self._prometheus_data = _PrometheusData(prometheus_registry)

        logger.info("Agent Service started")

    async def _get_init_data(self, context, trial_id):
        logger.debug(f"Trial [{trial_id}] - Processing init for service actor")

        last_received = False
        while True:
            request = await context.read()
            logger.debug(f"Trial [{trial_id}] - Read initial request: {request}")

            if request == grpc.aio.EOF:
                logger.info(f"Trial [{trial_id}] - Orchestrator disconnected service actor before start")
                return None

            if request.state == common_api.CommunicationState.NORMAL:
                if last_received:
                    error_str = (f"Trial [{trial_id}] - Received init data after 'LAST'")
                    logger.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

                if request.HasField("init_input"):
                    return request.init_input
                elif reply.HasField("details"):
                    logger.warning(f"Trial [{trial_id}] - Received unexpected detail data "
                                   f"[{reply.details}] before start")
                else:
                    data_set = request.WhichOneof("data")
                    error_str = (f"Trial [{trial_id}] - Received unexpected init data [{data_set}]")
                    logger.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

            elif request.state == common_api.CommunicationState.HEARTBEAT:
                reply = common_api.ActorRunTrialOutput()
                reply.state = request.state
                await context.write(reply)

            elif request.state == common_api.CommunicationState.LAST:
                if last_received:
                    error_str = (f"Trial [{trial_id}] - Before start, received unexpected 'LAST' "
                                    f"when waiting for 'END'")
                    logger.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

                logger.debug(f"Trial [{trial_id}] - Ending before init data")
                reply = common_api.ActorRunTrialOutput()
                reply.state = common_api.CommunicationState.LAST_ACK
                await context.write(reply)
                last_received = True

            elif request.state == common_api.CommunicationState.LAST_ACK:
                error_str = (f"Trial [{trial_id}] - Before start, received an unexpected 'LAST_ACK'")
                logger.error(error_str)
                await context.abort(grpc.StatusCode.UNKNOWN, error_str)

            elif request.state == common_api.CommunicationState.END:
                if request.HasField("details"):
                    logger.info(f"Trial [{trial_id}] - Ended before start [{request.details}]")
                else:
                    logger.debug(f"Trial [{trial_id}] - Ended before start")
                return None

            else:
                error_str = (f"Trial [{trial_id}] - Before start, received an invalid state "
                                f"[{request.state}] [{request}]")
                logger.error(error_str)
                await context.abort(grpc.StatusCode.UNKNOWN, error_str)

    def _start_session(self, trial_id, init_input):
        actor_impl = get_actor_impl(trial_id, self._impls, init_input)

        actor_name = init_input.actor_name
        actor_class = self._cog_settings.actor_classes.get(init_input.actor_class)
        if actor_class is None:
            raise CogmentError(f"Trial [{trial_id}] - "
                               f"Unknown class [{init_input.actor_class}] for service actor [{actor_name}]")

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

        self._prometheus_data.actors_started.labels(init_input.impl_name).inc()

        trial = Trial(trial_id, [], self._cog_settings)
        new_session = ActorSession(actor_impl.impl, actor_class, trial, actor_name, init_input.impl_name,
                                   init_input.env_name, config)
        new_session._prometheus_data = self._prometheus_data
        self._sessions.add(key)

        logger.debug(f"Trial [{trial_id}] - impl [{init_input.impl_name}] for service actor [{actor_name}] started")

        return new_session

    async def _run_session(self, context, session):
        send_task = None
        process_task = None

        try:
            send_task = asyncio.create_task(_process_outgoing(context, session))
            process_task = asyncio.create_task(_process_incoming(context, session))
            user_task = session._start_user_task()

            with self._prometheus_data.decide_request_time.labels(session.name, session.impl_name).time():
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

            self._prometheus_data.actors_ended.labels(session.impl_name).inc()

        except asyncio.CancelledError as exc:
            logger.debug(f"Trial [{session._trial.id}] - Actor [{session.name}] "
                         f"user implementation was cancelled")

        except Exception:
            logger.exception("run_session")
            raise

        finally:
            if send_task is not None:
                send_task.cancel()
            if process_task is not None:
                process_task.cancel()

    # Override
    async def RunTrial(self, request_iterator, context):
        if len(self._impls) == 0:
            logger.warning("No implementation registered on trial run request")
            raise CogmentError("No implementation registered")

        metadata = dict(context.invocation_metadata())
        trial_id = metadata["trial-id"]

        try:
            init_data = await asyncio.wait_for(self._get_init_data(context, trial_id), INIT_TIMEOUT)
            if init_data is None:
                return
            key = _trial_key(trial_id, init_data.actor_name)

            session = self._start_session(trial_id, init_data)

            await self._run_session(context, session)  # Blocking

            self._sessions.remove(key)

        except asyncio.TimeoutError:
            logger.error("Failed to receive init data from Orchestrator")

        except grpc._cython.cygrpc.AbortError:  # Exception from context.abort()
            pass

        except Exception:
            logger.exception("RunTrial")
            raise

    # Override
    async def Version(self, request, context):
        try:
            return list_versions()

        except Exception:
            logger.exception("Version")
            raise

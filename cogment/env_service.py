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

import grpc.aio  # type: ignore
from prometheus_client import Summary, Counter

import cogment.api.environment_pb2_grpc as env_grpc_api
import cogment.api.environment_pb2 as env_api
import cogment.api.common_pb2 as common_api

from cogment.utils import list_versions, logger, INIT_TIMEOUT
from cogment.session import RecvEvent, RecvMessage, ActorStatus, RecvAction, EventType
from cogment.session import _InitAck, _EndingAck, _Ending
from cogment.errors import CogmentError
from cogment.environment import EnvironmentSession
from cogment.trial import Trial

import asyncio
import time


class _PrometheusData:
    """Internal class holding the details of Prometheus report values for an environment."""

    def __init__(self, prometheus_registry):
        self.update_count_per_trial = Summary(
            "environment_update_count_per_trial",
            "Number of update by trial",
            ["impl_name"],
            registry=prometheus_registry
        )
        self.trial_duration = Summary(
            "environment_trial_duration_in_second", "Trial duration", ["trial_actor"],
            registry=prometheus_registry
        )
        self.trials_started = Counter(
            "environment_trials_started", "Number of trial started", ["impl_name"],
            registry=prometheus_registry
        )
        self.trials_ended = Counter(
            "environment_trials_ended", "Number of trial ended", ["impl_name"],
            registry=prometheus_registry
        )
        self.messages_received = Counter(
            "environment_received_messages",
            "Number of messages received",
            ["impl_name"],
            registry=prometheus_registry
        )
        self.messages_sent = Counter(
            "environment_sent_messages",
            "Number of messages sent",
            ["impl_name"],
            registry=prometheus_registry
        )

        pass


def _trial_key(trial_id, actor_name):
    return f"{trial_id}_{actor_name}"


def _process_normal_data(data, session):
    if session._trial.ending:
        recv_event = RecvEvent(EventType.ENDING)
    else:
        recv_event = RecvEvent(EventType.ACTIVE)

    if data.HasField("action_set"):
        logger.trace(f"Trial [{session._trial.id}] - Environment [{session.name}] received action set")

        act_set = data.action_set

        len_actions = len(act_set.actions)
        len_actors = len(session._trial.actors)

        if len_actions != len_actors:
            raise CogmentError(f"Received {len_actions} actions but have {len_actors} actors")

        tick_id = act_set.tick_id
        session._trial.tick_id = tick_id

        for index, actor in enumerate(session._trial.actors):
            if index in act_set.unavailable_actors:
                status = ActorStatus.UNAVAILABLE
                timestamp = 0
                action = None
            else:
                status = ActorStatus.ACTIVE
                timestamp = act_set.timestamp
                action = actor.actor_class.action_space()
                action.ParseFromString(act_set.actions[index])

            recv_event.actions.append(RecvAction(index, act_set.tick_id, status, timestamp, action))

        session._post_incoming_event((tick_id, recv_event))

    elif data.HasField("message"):
        logger.trace(f"Trial [{session._trial.id}] - Environment [{session.name}] received message")

        recv_event.messages = [RecvMessage(data.message)]
        session._post_incoming_event((-1, recv_event))

        session._prometheus_data.messages_received.labels(session.impl_name).inc()

    elif data.HasField("details"):
        logger.warning(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                       f"received unexpected detail data [{data.details}]")

    else:
        logger.error(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                     f"received unexpected data [{data.WhichOneof('data')}]")


async def _process_incoming(context, session):
    try:
        while True:
            data = await context.read()
            if data == grpc.aio.EOF:
                logger.info(f"Trial [{session._trial.id}] - Environment [{session.name}]: "
                            f"The orchestrator disconnected the environment")
                break
            logger.trace(f"Trial [{session._trial.id}] - Environment [{session.name}]: "
                         f"Received data [{data.state}] [{data.WhichOneof('data')}]")

            if data.state == common_api.CommunicationState.NORMAL:
                _process_normal_data(data, session)

            elif data.state == common_api.CommunicationState.HEARTBEAT:
                logger.trace(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                             f"received 'HEARTBEAT' and responding in kind")
                reply = env_api.EnvRunTrialOutput()
                reply.state = data.state
                await context.write(reply)

            elif data.state == common_api.CommunicationState.LAST:
                logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                             f"received 'LAST' state")
                session._trial.ending = True

            elif data.state == common_api.CommunicationState.LAST_ACK:
                logger.error(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                             f"received an unexpected 'LAST_ACK'")
                # TODO: Should we `return` or raise instead of continuing?

            elif data.state == common_api.CommunicationState.END:
                if session._trial.ending:
                    if data.HasField("details"):
                        logger.info(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                                    f"ended [{data.details}]")
                    else:
                        logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] ended")
                    session._post_incoming_event((-1, RecvEvent(EventType.FINAL)))
                else:
                    if data.HasField("details"):
                        details = data.details
                    else:
                        details = ""
                    logger.warning(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                                   f"ended forcefully [{details}]")

                session._trial.ended = True
                session._exit_queues()
                break

            else:
                logger.error(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                             f"received an invalid state [{data.state}]")

    except asyncio.CancelledError as exc:
        logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                     f"process incoming cancelled: [{exc}]")
        raise

    except Exception:
        logger.exception("_process_incoming")
        raise


async def _process_outgoing(context, session):
    try:
        async for data in session._retrieve_outgoing_data():
            package = env_api.EnvRunTrialOutput()
            package.state = common_api.CommunicationState.NORMAL

            # Using strict comparison: there is no reason to receive derived classes here
            if type(data) == env_api.ObservationSet:
                logger.trace(f"Trial [{session._trial.id}] - Environment [{session.name}]: "
                             f"Sending observation set")
                package.observation_set.CopyFrom(data)

            elif type(data) == common_api.Reward:
                logger.trace(f"Trial [{session._trial.id}] - Environment [{session.name}]: Sending reward")
                package.reward.CopyFrom(data)

            elif type(data) == common_api.Message:
                logger.trace(f"Trial [{session._trial.id}] - Environment [{session.name}]: Sending message")
                session._prometheus_data.messages_sent.labels(session.impl_name).inc()
                package.message.CopyFrom(data)

            elif type(data) == _InitAck:
                package.init_output.SetInParent()
                logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}]: Sending Init Data")

            elif type(data) == _Ending:
                package.state = common_api.CommunicationState.LAST
                logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}]: Sending 'LAST'")

            elif type(data) == _EndingAck:
                package.state = common_api.CommunicationState.LAST_ACK
                logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}]: Sending 'LAST_ACK'")
                await context.write(package)
                break

            else:
                logger.error(f"Trial [{session._trial.id}] - Environment [{session.name}]: "
                             f"Unknown data type to send [{type(data)}]")
                continue

            await context.write(package)

    except asyncio.CancelledError as exc:
        logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                     f"process outgoing cancelled: [{exc}]")
        raise

    except Exception:
        logger.exception("_process_outgoing")
        raise


class EnvironmentServicer(env_grpc_api.EnvironmentSPServicer):
    """Internal environment servicer class."""

    def __init__(self, env_impls, cog_settings, prometheus_registry=None):
        self._impls = env_impls
        self._sessions = set()
        self._cog_settings = cog_settings
        self._prometheus_data = _PrometheusData(prometheus_registry)

        logger.info("Environment Service started")

    async def _get_init_data(self, context, trial_id):
        logger.debug(f"Trial [{trial_id}] - Processing init for environment")

        last_received = False
        while True:
            request = await context.read()
            logger.debug(f"Trial [{trial_id}] - Read initial environment request: {request}")

            if request == grpc.aio.EOF:
                logger.info(f"Trial [{trial_id}] - Orchestrator disconnected environment before start")
                return None

            if request.state == common_api.CommunicationState.NORMAL:
                if last_received:
                    error_str = (f"Trial [{trial_id}] - Environment received init data after 'LAST'")
                    logger.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

                if request.HasField("init_input"):
                    return request.init_input
                elif reply.HasField("details"):
                    logger.warning(f"Trial [{trial_id}] - Received unexpected detail data "
                                   f"[{reply.details}] before start")
                else:
                    data_set = request.WhichOneof("data")
                    error_str = (f"Trial [{trial_id}] - Environment received unexpected init data [{data_set}]")
                    logger.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

            elif request.state == common_api.CommunicationState.HEARTBEAT:
                reply = env_api.EnvRunTrialOutput()
                reply.state = request.state
                await context.write(reply)

            elif request.state == common_api.CommunicationState.LAST:
                if last_received:
                    error_str = (f"Trial [{trial_id}] - Before start, environment "
                                 f"received unexpected 'LAST' when waiting for 'END'")
                    logger.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

                logger.debug(f"Trial [{trial_id}] - Ending before init data")
                reply = env_api.EnvRunTrialOutput()
                reply.state = common_api.CommunicationState.LAST_ACK
                await context.write(reply)
                last_received = True

            elif request.state == common_api.CommunicationState.LAST_ACK:
                error_str = (f"Trial [{trial_id}] - Before start, environment received an unexpected 'LAST_ACK'")
                logger.error(error_str)
                await context.abort(grpc.StatusCode.UNKNOWN, error_str)

            elif request.state == common_api.CommunicationState.END:
                if request.HasField("details"):
                    logger.info(f"Trial [{trial_id}] - Ended before environment start [{request.details}]")
                else:
                    logger.debug(f"Trial [{trial_id}] - Ended before environment start")
                return None

            else:
                error_str = (f"Trial [{trial_id}] - Before start, environment "
                             f"received an invalid state [{request.state}] [{request}]")
                logger.error(error_str)
                await context.abort(grpc.StatusCode.UNKNOWN, error_str)

    def _start_session(self, trial_id, init_input):
        name = init_input.name
        if not name:
            raise CogmentError(f"Trial [{trial_id}] - Empty environment name")

        if init_input.impl_name:
            impl_name = init_input.impl_name
            impl = self._impls.get(impl_name)
            if impl is None:
                raise CogmentError(f"Trial [{trial_id}] - "
                                   f"Unknown impl [{impl_name}] for environment [{name}]")
        else:
            impl_name, impl = next(iter(self._impls.items()))
            logger.info(f"Trial [{trial_id}] - "
                        f"impl [{impl_name}] arbitrarily chosen for environment [{name}]")

        key = _trial_key(trial_id, name)
        if key in self._sessions:
            raise CogmentError(f"Trial [{trial_id}] - Environment [{name}] already exists")

        config = None
        if init_input.HasField("config"):
            env_config_type = self._cog_settings.environment.config_type
            if env_config_type is None:
                raise CogmentError(f"Trial [{trial_id}] - Environment [{name}] "
                                   f"received config data of unknown type (was it defined in cogment.yaml?)")
            config = env_config_type()
            config.ParseFromString(init_input.config.content)

        self._prometheus_data.trials_started.labels(impl_name).inc()

        trial = Trial(trial_id, init_input.actors_in_trial, self._cog_settings)
        trial.tick_id = init_input.tick_id
        new_session = EnvironmentSession(impl.impl, trial, name, impl_name, config)
        new_session._prometheus_data = self._prometheus_data
        self._sessions.add(key)

        logger.debug(f"Trial [{trial_id}] - impl [{impl_name}] for environment [{name}] started")

        return new_session

    async def _run_session(self, context, session):
        send_task = None
        process_task = None

        try:
            send_task = asyncio.create_task(_process_outgoing(context, session))
            process_task = asyncio.create_task(_process_incoming(context, session))
            user_task = session._start_user_task()

            with self._prometheus_data.trial_duration.labels(session.impl_name).time():
                logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] session started")
                normal_return = await user_task

            self._prometheus_data.update_count_per_trial.labels(session.impl_name).observe(session._trial.tick_id)

            if normal_return:
                if not session._last_event_delivered:
                    logger.warning(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                                   f"user implementation returned before required")
                else:
                    logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                                 f"user implementation returned")
            else:
                logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                             f"user implementation was cancelled")

            self._prometheus_data.trials_ended.labels(session.impl_name).inc()

        except asyncio.CancelledError as exc:
            logger.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                         f"user implementation was cancelled with exception [{exc}]")

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
            key = _trial_key(trial_id, init_data.name)

            session = self._start_session(trial_id, init_data)

        except asyncio.TimeoutError:
            logger.error("Failed to receive init data from Orchestrator")

        except grpc._cython.cygrpc.AbortError:  # Exception from context.abort()
            raise

        except asyncio.CancelledError as exc:
            logger.debug(f"Trial [{trial_id}] - Environment start cancelled: [{exc}]")
            raise

        except Exception:
            logger.exception("RunTrial")
            raise

        else:
            await self._run_session(context, session)  # Blocking
            self._sessions.remove(key)

    # Override
    async def Version(self, request, context):
        try:
            return list_versions()

        except Exception:
            logger.exception("Version")
            raise

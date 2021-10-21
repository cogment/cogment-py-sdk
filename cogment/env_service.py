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

from abc import ABC, abstractmethod

import cogment.api.environment_pb2_grpc as grpc_api

import cogment.api.environment_pb2 as env_api
import cogment.api.common_pb2 as common_api
from cogment.utils import list_versions, TRACE
from cogment.session import RecvEvent, RecvMessage, RecvAction, EventType, _EndingAck, _Ending
from cogment.errors import CogmentError

import grpc.aio  # type: ignore

from cogment.environment import EnvironmentSession

from cogment.trial import Trial

from prometheus_client import Summary, Counter

import logging
import asyncio


class _PrometheusData:
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
        logging.log(TRACE, f"Trial [{session._trial.id}] - Environment [{session.name}] received action set")

        len_actions = len(data.action_set.actions)
        len_actors = len(session._trial.actors)

        if len_actions != len_actors:
            raise CogmentError(f"Received {len_actions} actions but have {len_actors} actors")

        tick_id = data.action_set.tick_id
        session._trial.tick_id = tick_id

        for i, actor in enumerate(session._trial.actors):
            action = actor.actor_class.action_space()
            action.ParseFromString(data.action_set.actions[i])
            recv_event.actions.append(RecvAction(i, action, tick_id))

        session._new_event(recv_event)

    elif data.HasField("message"):
        logging.log(TRACE, f"Trial [{session._trial.id}] - Environment [{session.name}] received message")

        session._prometheus_data.messages_received.labels(session.impl_name).inc()

        recv_event.messages = [RecvMessage(data.message)]
        session._new_event(recv_event)

    elif data.HasField("details"):
        logging.warning(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                        f"received unexpected detail data [{data.details}]")

    else:
        logging.error(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                      f"received unexpected data [{data.WhichOneof('data')}]")


async def _process_incoming(context, session):
    try:
        while True:
            data = await context.read()
            if data == grpc.aio.EOF:
                logging.info(f"Trial [{session._trial.id}] - Environment [{session.name}]: "
                             f"The orchestrator disconnected the environment")
                break
            logging.log(TRACE, f"Trial [{session._trial.id}] - Environment [{session.name}]: "
                               f"Received data [{data.state}] [{data.WhichOneof('data')}]")

            if data.state == common_api.CommunicationState.NORMAL:
                _process_normal_data(data, session)

            elif data.state == common_api.CommunicationState.HEARTBEAT:
                logging.log(TRACE, f"Trial [{session._trial.id}] - Environment [{session.name}] "
                                   f"received 'HEARTBEAT' and responding in kind")
                reply = env_api.EnvRunTrialOutput()
                reply.state = data.state
                await context.write(reply)

            elif data.state == common_api.CommunicationState.LAST:
                logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                              f"received 'LAST' state")
                session._trial.ending = True

            elif data.state == common_api.CommunicationState.LAST_ACK:
                logging.error(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                              f"received an unexpected 'LAST_ACK'")
                # TODO: Should we `return` or raise instead of continuing?

            elif data.state == common_api.CommunicationState.END:
                if session._trial.ending:
                    if data.HasField("details"):
                        logging.info(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                                     f"ended [{data.details}]")
                    else:
                        logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] ended")
                    session._new_event(RecvEvent(EventType.FINAL))
                else:
                    if data.HasField("details"):
                        details = data.details
                    else:
                        details = ""
                    logging.warning(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                                    f"ended forcefully [{details}]")

                session._trial.ended = True
                session._exit_queues()
                break

            else:
                logging.error(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                              f"received an invalid state [{data.state}]")

    except asyncio.CancelledError as exc:
        logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] coroutine cancelled: [{exc}]")
        raise

    except Exception:
        logging.exception("_process_incoming")
        raise


async def _process_outgoing(context, session):
    try:
        async for data in session._retrieve_data():
            package = env_api.EnvRunTrialOutput()
            package.state = common_api.CommunicationState.NORMAL

            # Using strict comparison: there is no reason to receive derived classes here
            if type(data) == env_api.ObservationSet:
                logging.log(TRACE, f"Trial [{session._trial.id}] - Environment [{session.name}]: "
                                   f"Sending observation set")
                package.observation_set.CopyFrom(data)

            elif type(data) == common_api.Reward:
                logging.log(TRACE, f"Trial [{session._trial.id}] - Environment [{session.name}]: Sending reward")
                package.reward.CopyFrom(data)

            elif type(data) == common_api.Message:
                logging.log(TRACE, f"Trial [{session._trial.id}] - Environment [{session.name}]: Sending message")
                session._prometheus_data.messages_sent.labels(session.impl_name).inc()
                package.message.CopyFrom(data)

            elif type(data) == _Ending:
                package.state = common_api.CommunicationState.LAST
                logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}]: Sending 'LAST'")

            elif type(data) == _EndingAck:
                package.state = common_api.CommunicationState.LAST_ACK
                logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}]: Sending 'LAST_ACK'")
                await context.write(package)
                break

            else:
                logging.error(f"Trial [{session._trial.id}] - Environment [{session.name}]: "
                              f"Unknown data type to send [{type(data)}]")
                continue

            await context.write(package)

    except asyncio.CancelledError as exc:
        logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                      f"process outgoing cancelled: [{exc}]")
        raise

    except Exception:
        logging.exception("_process_outgoing")
        raise


class EnvironmentServicer(grpc_api.EnvironmentSPServicer):
    def __init__(self, env_impls, cog_settings, prometheus_registry=None):
        self.__impls = env_impls
        self._sessions = set()
        self.__cog_settings = cog_settings
        self._prometheus_data = _PrometheusData(prometheus_registry)

        logging.info("Environment Service started")

    async def _get_init_data(self, context, trial_id):
        logging.debug(f"Trial [{trial_id}] - Processing init for environment")

        last_received = False
        while True:
            # TODO: Limit the time to wait for init data
            request = await context.read()
            logging.debug(f"Trial [{trial_id}] - Read initial environment request: {request}")

            if request == grpc.aio.EOF:
                logging.info(f"Trial [{trial_id}] - Orchestrator disconnected environment before start")
                return None

            if request.state == common_api.CommunicationState.NORMAL:
                if last_received:
                    error_str = (f"Trial [{trial_id}] - Environment received init data after 'LAST'")
                    logging.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

                if request.HasField("init_input"):
                    return request.init_input
                else:
                    data_set = request.WhichOneof("data")
                    error_str = (f"Trial [{trial_id}] - Environment received unexpected init data [{data_set}]")
                    logging.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

            elif request.state == common_api.CommunicationState.HEARTBEAT:
                reply = env_api.EnvRunTrialOutput()
                reply.state = request.state
                await context.write(reply)

            elif request.state == common_api.CommunicationState.LAST:
                if last_received:
                    error_str = (f"Trial [{trial_id}] - Before start, environment "
                                 f"received unexpected 'LAST' when waiting for 'END'")
                    logging.error(error_str)
                    await context.abort(grpc.StatusCode.UNKNOWN, error_str)

                logging.debug(f"Trial [{trial_id}] - Ending before init data")
                reply = env_api.EnvRunTrialOutput()
                reply.state = common_api.CommunicationState.LAST_ACK
                await context.write(reply)
                last_received = True

            elif request.state == common_api.CommunicationState.LAST_ACK:
                error_str = (f"Trial [{trial_id}] - Before start, environment received an unexpected 'LAST_ACK'")
                logging.error(error_str)
                await context.abort(grpc.StatusCode.UNKNOWN, error_str)

            elif request.state == common_api.CommunicationState.END:
                if request.HasField("details"):
                    logging.info(f"Trial [{trial_id}] - Ended before environment start [{request.details}]")
                else:
                    logging.debug(f"Trial [{trial_id}] - Ended before environment start")
                return None

            else:
                error_str = (f"Trial [{trial_id}] - Before start, environment "
                             f"received an invalid state [{request.state}] [{request}]")
                logging.error(error_str)
                await context.abort(grpc.StatusCode.UNKNOWN, error_str)

    def _start_session(self, trial_id, init_input):
        name = init_input.name
        if not name:
            raise CogmentError(f"Trial [{trial_id}] - Empty environment name")

        if init_input.impl_name:
            impl_name = init_input.impl_name
            impl = self.__impls.get(impl_name)
            if impl is None:
                raise CogmentError(f"Trial [{trial_id}] - "
                                   f"Unknown impl [{impl_name}] for environment [{name}]")
        else:
            impl_name, impl = next(iter(self.__impls.items()))
            logging.info(f"Trial [{trial_id}] - "
                         f"impl [{impl_name}] arbitrarily chosen for environment [{name}]")

        key = _trial_key(trial_id, name)
        if key in self._sessions:
            raise CogmentError(f"Trial [{trial_id}] - Environment [{name}] already exists")

        config = None
        if init_input.HasField("config"):
            env_config_type = self.__cog_settings.environment.config_type
            if env_config_type is None:
                raise CogmentError(f"Trial [{trial_id}] - Environment [{name}] "
                                   f"received config data of unknown type (was it defined in cogment.yaml?)")
            config = env_config_type()
            config.ParseFromString(init_input.config.content)

        self._prometheus_data.trials_started.labels(impl_name).inc()

        trial = Trial(trial_id, init_input.actors_in_trial, self.__cog_settings)
        trial.tick_id = init_input.tick_id
        new_session = EnvironmentSession(impl.impl, trial, name, impl_name, config)
        new_session._prometheus_data = self._prometheus_data
        self._sessions.add(key)

        logging.debug(f"Trial [{trial_id}] - impl [{impl_name}] for environment [{name}] started")

        return new_session

    async def _run_session(self, context, session):
        send_task = None
        process_task = None

        try:
            send_task = asyncio.create_task(_process_outgoing(context, session))
            process_task = asyncio.create_task(_process_incoming(context, session))
            user_task = session._start_user_task()

            with self._prometheus_data.trial_duration.labels(session.impl_name).time():
                logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] session started")
                normal_return = await user_task

            self._prometheus_data.update_count_per_trial.labels(session.impl_name).observe(session._trial.tick_id)

            if normal_return:
                if not session._last_event_delivered:
                    logging.warning(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                                    f"user implementation returned before required")
                else:
                    logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                                  f"user implementation returned")
            else:
                logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                              f"user implementation was cancelled")

            self._prometheus_data.trials_ended.labels(session.impl_name).inc()

        except asyncio.CancelledError as exc:
            logging.debug(f"Trial [{session._trial.id}] - Environment [{session.name}] "
                          f"user implementation was cancelled with exception")

        except Exception:
            logging.exception("run_session")
            raise

        finally:
            if send_task is not None:
                send_task.cancel()
            if process_task is not None:
                process_task.cancel()

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
            key = _trial_key(trial_id, init_data.name)

            session = self._start_session(trial_id, init_data)

            init_msg = env_api.EnvRunTrialOutput()
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

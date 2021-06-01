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

import asyncio
import logging
import traceback
from abc import ABC, abstractmethod


class DatalogSession(ABC):
    """This represents a datalogger working locally."""

    def __init__(self, impl, trial_id, trial_params, raw_trial_params):
        self.trial_id = trial_id
        self.trial_params = trial_params
        self.raw_trial_params = raw_trial_params

        self._task = None
        self._impl = impl
        self.__queue = None

    def start(self):
        self.__queue = asyncio.Queue()

    async def get_all_samples(self):
        if self.__queue is not None:
            while True:
                try:
                    sample = await self.__queue.get()
                    if sample is None:
                        break
                    keep_looping = yield sample
                    if keep_looping is not None and not bool(keep_looping):
                        break

                    self.__queue.task_done()

                except GeneratorExit:
                    raise

                except asyncio.CancelledError:
                    logging.debug("Datalog coroutine cancelled while waiting for a sample.")
                    break

    def _new_sample(self, sample):
        if self.__queue is not None:
            self.__queue.put_nowait(sample)
        else:
            logging.warning("Datalog received a sample that it was unable to handle.")

    async def _run(self):
        try:
            await self._impl(self)
            return True

        except asyncio.CancelledError:
            logging.debug(f"Datalog implementation coroutine cancelled")
            return False

        except Exception:
            logging.error(f"An exception occured in user datalog implementation:\n{traceback.format_exc()}")
            raise

    def __str__(self):
        result = f"DatalogSession: trial_id = {self.trial_id}, trial_params = {self.trial_params}"
        result += f", raw_trial_params = {self.raw_trial_params}"
        return result


class _ServedDatalogSession(DatalogSession):
    def __init__(self, impl, trial_id, trial_params, raw_trial_params):
        super().__init__(impl, trial_id, trial_params, raw_trial_params)

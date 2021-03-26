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

import asyncio
import logging
import traceback
from abc import ABC, abstractmethod


class DatalogSession(ABC):
    """This represents a datalogger working locally."""

    def __init__(self, impl, trial_id, trial_params):
        self.trial_id = trial_id
        self.trial_params = trial_params

        self._task = None
        self.__impl = impl
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
                    yield sample

                    self.__queue.task_done()

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
            await self.__impl(self)
        except Exception:
            logging.error(f"An exception occured in user datalog implementation:\n{traceback.format_exc()}")
            raise


class _ServedDatalogSession(DatalogSession):
    def __init__(self, impl, trial_id, trial_params):
        super().__init__(impl, trial_id, trial_params)

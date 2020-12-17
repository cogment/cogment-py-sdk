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

    def __init__(self, impl, trial, trial_params):
        self.trial_id = trial.id
        self.trial_params = trial_params

        self.on_sample = None
        self.on_trial_over = None

        self._started = False
        self._task = None

        self.__impl = impl
        self.__sample_future = None

    def start(self):
        self._started = True

    async def _end(self):
        if self.on_trial_over is not None:
            self.on_trial_over()
        self.__sample_future = None

    async def get_sample(self):
        assert self.on_sample is None

        self.__sample_future = asyncio.get_running_loop().create_future()
        return await self.__sample_future

    async def get_all_samples(self):
        while True:
            sample = await self.get_sample()
            if sample is None:
                break
            yield sample

    def _new_sample(self, sample):
        if self.on_sample is not None:
            self.on_sample(sample)
            self.__sample_future = None
        elif self.__sample_future is not None:
            self.__sample_future.set_result(sample)
            self.__sample_future = None
        else:
            logging.warning("A sample was missed")

    async def _run(self):
        try:
            await self.__impl(self)
        except Exception:
            logging.error(f"An exception occured in user datalog implementation:\n{traceback.format_exc()}")
            raise


class _ServedDatalogSession(DatalogSession):
    def __init__(self, impl, trial, trial_params):
        super().__init__(impl, trial, trial_params)

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


class DatalogSession():
    """Class representing the session of a datalog for a trial."""

    def __init__(self, impl, trial_id, user_id, trial_params):
        self.trial_id = trial_id
        self.user_id = user_id
        self.trial_params = trial_params

        self._user_task = None
        self._impl = impl
        self.__queue = None

    def __str__(self):
        result = f"DatalogSession: trial_id = {self.trial_id}, trial_params = {self.trial_params}"
        return result

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
                    self.__queue.task_done()
                    if keep_looping is not None and not bool(keep_looping):
                        break

                except GeneratorExit:
                    raise

                except asyncio.CancelledError as exc:
                    logging.debug(f"Datalog coroutine cancelled while waiting for a sample: [{exc}]")
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

        except asyncio.CancelledError as exc:
            logging.debug(f"Datalog implementation coroutine cancelled: [{exc}]")
            return False

        except Exception:
            logging.exception(f"An exception occured in user datalog implementation:")
            raise

    def _start_user_task(self):
        self._user_task = asyncio.create_task(self._run())
        return self._user_task

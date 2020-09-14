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

import cogment
import cog_settings

import data_pb2
import asyncio

import logging

async def my_datalog(data, trial_params, trial_id):

    print(f"trial_params - {trial_params}")

    decode_all = cogment.DecodeData(trial_params, cog_settings)

    async for sample in data:

        observations, actions, rewards = decode_all.decode_datasample(sample)
        print(f"trial_id - {trial_id}\n obs - {observations}\n actions - {actions}\n rewards {rewards}")

async def main():
    server = cogment.Server(cog_project=cog_settings, port=9001)

    server.register_datalog(impl=my_datalog)

    await server.run()


asyncio.run(main())

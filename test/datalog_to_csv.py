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
import csv
import os

from cogment.delta_encoding import DecodeObservationData

from google.protobuf.json_format import MessageToJson

csv_filename = os.getenv('CSV_FILENAME').rstrip()

async def write_it(line, mode):
    file = open(csv_filename, mode, newline ='') 
    with file:
        write = csv.writer(file)
        write.writerows([line])


async def my_datalog(data, trial_params, trial_id):

    print(f"trial_params - {trial_params}")

    trial_config = MessageToJson(
                        trial_params.trial_config, True)

    columns = ["trial_id", "tick_id", "timestamp", "trial_config"]
    last_obs = []

    actor_classes_list = [actor.id_ for actor in cog_settings.actor_classes]
    trial_actor_list = [actor.actor_class for actor in trial_params.actors]
    actor_counts = [0] * len(actor_classes_list)
    for index, actor_class in enumerate(actor_classes_list):
        actor_counts[index] += trial_actor_list.count(actor_class)

    for ac_index, actor_class in enumerate(cog_settings.actor_classes):
        count = actor_counts[ac_index]

        cols_obs = [
            x.name for x in actor_class.observation_space.DESCRIPTOR.fields]
        cols_actions = [
            x.name for x in actor_class.action_space.DESCRIPTOR.fields]
        cols_rewards = ["value", "confidence"]
        cols_messages = ["messages"]
        last_obs.extend([None] * count)

        for j in range(count):
            name = f"{actor_class.id_}_{j}"
            obs_title = [f"{name}_observation"]
            action_title = [f"{name}_action"]
            reward_title = [f"{name}_reward_{x}" for x in cols_rewards]
            message_title = [f"{name}_message_{x}" for x in cols_messages]
            columns.extend(obs_title)
            columns.extend(action_title)
            columns.extend(reward_title)
            columns.extend(message_title)

    if not os.path.isfile(csv_filename):
        await write_it(columns, "w+")

    async for sample in data:

        row = [
            trial_id,
            sample.observations.tick_id,
            sample.observations.timestamp / 1000000000,
            trial_config
        ]

        actor_id = 0
        for ac_index, actor_class in enumerate(cog_settings.actor_classes):
            count = actor_counts[ac_index]
            for j in range(count):
                try:
                    obs_id = sample.observations.actors_map[
                        actor_id]
                except Exception:
                    print(sample)

                obs_data = sample.observations.observations[obs_id]
                action_data = sample.actions[actor_id].content

                obs = DecodeObservationData(
                    actor_class, obs_data, last_obs[actor_id])
                last_obs[actor_id] = obs

                row.append(MessageToJson(
                    obs,  including_default_value_fields=True))
                row.append(MessageToJson(sample.actions[
                           actor_id],  including_default_value_fields=True))

                row.append(sample.rewards[actor_id].value)

                row.append(sample.rewards[actor_id].confidence)

                row.append(MessageToJson(sample.messages[actor_id], including_default_value_fields=True))

                actor_id += 1

        await write_it(row, 'a+')


async def main():
    server = cogment.Server(cog_project=cog_settings, port=9001)

    server.register_datalog(impl=my_datalog)

    await server.run()


asyncio.run(main())

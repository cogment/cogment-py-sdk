import cogment
import cog_settings

import os
import data_pb2
import asyncio

from cogment.delta_encoding import DecodeObservationData

import pandas as pd
from sqlalchemy import create_engine
from google.protobuf.json_format import MessageToJson

table_name = os.getenv('POSTGRES_TABLENAME')
postgres_engine = os.getenv('POSTGRES_ENGINE')

engine = create_engine(postgres_engine, echo=False)

async def my_datalog(data, trial_params, trial_id):

    connection = engine.connect()

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

        df = pd.DataFrame([row], columns=columns)

        df.to_sql(table_name, connection, if_exists='append')


async def main():
    server = cogment.Server(cog_project=cog_settings, port=9001)

    server.register_datalog(impl=my_datalog)

    await server.run()


asyncio.run(main())

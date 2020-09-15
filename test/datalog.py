import cogment
import cog_settings

import data_pb2
import asyncio

import logging

async def my_datalog(data, trial_params, trial_id):

    print(f"trial_params - {trial_params}")

    decode_all = cogment.DecodeData(trial_params, cog_settings)

    async for sample in data:

        observations, actions, rewards, messages = decode_all.decode_datasample(sample)
        print(f"\ntrial_id: {trial_id}\nobs: {observations}\nactions: {actions}\nrewards: {rewards}\nmessages: {messages}")


async def main():
    server = cogment.Server(cog_project=cog_settings, port=9001)

    server.register_datalog(impl=my_datalog)

    await server.run()


asyncio.run(main())

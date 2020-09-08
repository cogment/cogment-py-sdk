import grpc
from cogment.api.environment_pb2 import EnvStartRequest, EnvStartReply, EnvEndRequest, EnvEndReply, EnvUpdateRequest, EnvUpdateReply, ActionSet
import cogment.api.environment_pb2_grpc
from cogment.api.hooks_pb2 import TrialContext
import cogment.api.hooks_pb2_grpc
from cogment.api.common_pb2 import TrialActor, TrialParams, TrialConfig, EnvironmentParams, EnvironmentConfig, TrialConfig, ActorParams
import data_pb2
import time
import grpc.experimental.aio
import asyncio
from queue import Queue


async def main():
    async with grpc.experimental.aio.insecure_channel('localhost:9001') as channel:
        stub = cogment.api.hooks_pb2_grpc.TrialHooksStub(channel)

        # initialize trial_config
        orig_env_config = data_pb2.EnvConfig(
            num_agents=4,
            str_test="Weekend!"
        )
        orig_trial_config = data_pb2.TrialConfig(env_config=orig_env_config)
        trial_config = TrialConfig()
        trial_config.content = orig_trial_config.SerializeToString()

        # initialize environment (params)
        environment_params = EnvironmentParams(endpoint="grpc://env:9000")

        actor_param_list = [
            ActorParams(
                actor_class="player",
                endpoint="grpc://player:9000"),
            ActorParams(
                actor_class="player",
                endpoint="grpc://player:9000")
        ]

        trial_params = TrialParams(
            trial_config = trial_config,
            environment = environment_params,
            actors = actor_param_list,
            max_steps = 3
        )

        pre_trial = stub.PreTrial(
            TrialContext(
                impl_name="release",
                params = trial_params
            ),
            metadata=(("trial-id", "abc"),)
        )

        tmp = await pre_trial

        print("Params list - ", tmp.params)


asyncio.run(main())

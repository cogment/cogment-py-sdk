import grpc
from cogment.api.data_pb2 import DatalogMsg, DatalogSample
import cogment.api.data_pb2_grpc
from cogment.api.common_pb2 import Message, Feedback, Action, TrialActor, TrialParams, TrialConfig, EnvironmentParams, EnvironmentConfig, TrialConfig, ActorParams, ObservationData
from cogment.api.agent_pb2 import Reward, MessageCollection
from cogment.api.environment_pb2 import ObservationSet

import data_pb2
import time
import grpc.experimental.aio
import asyncio
from queue import Queue

def send_trialparams_req():

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

    req = DatalogMsg(trial_params=trial_params)

    return req



def send_datalogsample_req(user_id, obs_value_list, act_value_list):

    # Observations
    observation_set = ObservationSet()

    obs = data_pb2.Observation(value=obs_value_list[0])
    obs_data = ObservationData()
    obs_data.snapshot = True
    obs_data.content = obs.SerializeToString()
    observation_set.observations.append(obs_data)
    observation_set.actors_map.append(0)

    obs = data_pb2.Observation(value=obs_value_list[1])
    obs_data = ObservationData()
    obs_data.snapshot = True
    obs_data.content = obs.SerializeToString()
    observation_set.observations.append(obs_data)
    observation_set.actors_map.append(1)

    # DataSample
    data_sample = DatalogSample(user_id=user_id,
        observations=observation_set
        )

    # Actions
    action = data_pb2.Action(value=act_value_list[0])
    action.SerializeToString()
    b_action = Action()
    b_action.content = action.SerializeToString()
    data_sample.actions.append(b_action)
    action = data_pb2.Action(value=act_value_list[1])
    action.SerializeToString()
    b_action = Action()
    b_action.content = action.SerializeToString()
    data_sample.actions.append(b_action)

    # Rewards
    feedback = Feedback(actor_id=0,
        tick_id=1,
        value=1.0,
        confidence=1.0
        )
    reward = Reward(value=0.5,
        confidence=1.0
        )
    reward.feedbacks.append(feedback)
    reward.feedbacks.append(feedback)
    data_sample.rewards.append(reward)
    data_sample.rewards.append(reward)

    # Messages
    msg_test = data_pb2.MessageTest(name="Doctor Zhivago")
    message = Message(sender_id=0,
        receiver_id=1
        )
    message.payload.Pack(msg_test)
    message_collection = MessageCollection()
    message_collection.messages.append(message)
    message_collection.messages.append(message)
    data_sample.messages.append(message_collection)
    data_sample.messages.append(message_collection)

    req = DatalogMsg(sample=data_sample)

    return req


async def main():
    async with grpc.experimental.aio.insecure_channel('localhost:9001') as channel:
        stub = cogment.api.data_pb2_grpc.LogExporterStub(channel)

        stream_a = stub.Log(metadata=(("trial-id", "abc"),))
        stream_b = stub.Log(metadata=(("trial-id", "def"),))

        await stream_a.write(send_trialparams_req())
        await stream_b.write(send_trialparams_req())

        for count in range(3):
            await stream_a.write(send_datalogsample_req(user_id="abc_"+str(count), obs_value_list=[22+count,23+count], act_value_list=[33+count,34+count]))
            await stream_b.write(send_datalogsample_req(user_id="def_"+str(count), obs_value_list=[44+count,45+count], act_value_list=[55+count,56+count]))

        await stream_a.done_writing()
        await stream_b.done_writing()
        await stream_a
        await stream_b

asyncio.run(main())

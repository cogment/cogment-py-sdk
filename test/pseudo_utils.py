import grpc
from cogment.api.agent_pb2 import AgentStartRequest, AgentDataRequest, AgentActionReply, AgentRewardRequest, Reward
import cogment.api.agent_pb2_grpc
from cogment.api.common_pb2 import TrialActor
import data_pb2
import time
import grpc.experimental.aio
import asyncio
from queue import Queue

# use following block in agent main
        # trial_act_list = [(("trial-id", "abc"), ("actor-id", "0")),
        #               (("trial-id", "abc"), ("actor-id", "1"))]

        # for count in range(3):
        #     tmp_list, action_list = await doit.do_decides(trial_act_list, count)
        #     for actor_index, action in enumerate(action_list):
        #         print(f"++Recieved from actor {actor_index} - {action}")
        #         print(f'++Feedback value from actor {actor_index}',tmp_list[actor_index].feedbacks)
            # await doit.return_rewards(tmp_list)

def make_req(val, final=False):
    obs = data_pb2.Observation(value=val)
    req = AgentDataRequest()
    req.observation.data.snapshot = True
    req.observation.data.content = obs.SerializeToString()
    req.observation.tick_id = 12

    req.final = final
    return req


async def send_starts(stub):
	await stub.Start(
	  AgentStartRequest(
	      impl_name="blearg",
	      actors_in_trial=[
	        TrialActor(actor_class="player", name="Joe"),
	        TrialActor(actor_class="player", name="Jack")
	      ]),
	  metadata=(("trial-id", "abc"), ("actor-id", "0"))
	)

	await stub.Start(
	  AgentStartRequest(
	      impl_name="blearg",
	      actors_in_trial=[
	        TrialActor(actor_class="player", name="Joe"),
	        TrialActor(actor_class="player", name="Jack")
	      ]), 
	  metadata=(("trial-id", "abc"), ("actor-id", "1"))
	)

	# await stub.Start(
	#   AgentStartRequest( 
	#       impl_name="blearg",
	#       actors_in_trial=[
	#         TrialActor(actor_class="player", name="Joe")           
	#       ]), 
	#   metadata=(("trial-id", "def"), ("actor-id", "0"))
	# )

async def do_decides(stub, trial_act_list, obs_value):
	tmp_list = []
	act_list = []
	for trial_act in trial_act_list:
		decide_conn = stub.Decide(metadata=trial_act)
		await decide_conn.write(make_req(obs_value))
		tmp = await decide_conn.read()
		act = data_pb2.Action()
		act.ParseFromString(tmp.action.content)
		tmp_list.append(tmp)
		act_list.append(act)
	return tmp_list, act_list

async def return_rewards(stub, tmp_list):
	feedback_list = [[] for i in range(len(tmp_list))]
	values_list = [[] for i in range(len(tmp_list))]
	new_values_list =  []
	for idx in range(len(tmp_list)):
		for feedback in tmp_list[idx].feedbacks:
			feedback_list[feedback.actor_id].append(feedback)
			values_list[feedback.actor_id].append(feedback.value)
	for idx in range(len(tmp_list)):
		new_values_list.append(sum(values_list[idx])/float(len(values_list[idx])))
		print(f"FFFF{idx}{idx}{idx}{idx}",feedback_list[idx],f"VVV{idx}{idx}{idx}",new_values_list[idx])
	for idx in range(len(tmp_list)):
		reward = Reward(value = new_values_list[idx],
					confidence = 1.0)
		reward.feedbacks.extend(feedback_list[idx])

		await stub.Reward(
			AgentRewardRequest(
				trial_id = "abc",
				actor_id = idx,
				tick_id = -1,
				reward = reward), 
				metadata=(("trial-id", "abc"), ("actor-id", str(idx)))
				)

# async def end_trial(stub):

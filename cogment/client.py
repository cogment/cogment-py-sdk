import grpc

from cogment.api.orchestrator_pb2_grpc import TrialLifecycleStub, ActorEndpointStub
from cogment.api.orchestrator_pb2 import TrialStartRequest
from cogment.trial import TrialLifecycle

class Connection:
    def __init__(self, cog_project, endpoint):
        self.cog_project = cog_project

        channel = grpc.insecure_channel(endpoint)

        self.__lifecycle_stub = TrialLifecycleStub(channel)
        self.__actor_stub = ActorEndpointStub(channel)

    async def start_trial(self, trial_config, user_id):
        req = TrialStartRequest()
        req.config.content = trial_config.SerializeToString()
        req.user_id = user_id

        rep = await self.__lifecycle_stub.StartTrial(req)

        return TrialLifecycle(rep.trial_id, self.cog_project, rep.actors_in_trial)


    def join_trial(self, trial_id, actor_id, actor_class, impl):
        pass

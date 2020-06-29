from cogment.grpc_server import GrpcServer
from cogment.env_service import Environment

import fixtures.cog_settings as settings


class Env(Environment):
    pass


if __name__ == "__main__":
    server = GrpcServer(Env, settings)
    server.serve()

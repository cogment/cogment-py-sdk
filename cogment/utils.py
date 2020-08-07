from cogment.api.common_pb2 import VersionInfo
from cogment.version import __version__

import grpc


def list_versions():
    reply = VersionInfo()
    reply.versions.add(name='cogment_sdk', version=__version__)
    reply.versions.add(name='grpc', version=grpc.__version__)

    return reply

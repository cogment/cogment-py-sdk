from cogment.api.common_pb2 import VersionInfo
from cogment.version import __version__

import grpc


def list_versions(cls):
    reply = VersionInfo()
    reply.versions.add(name='cogment_sdk', version=__version__)
    reply.versions.add(name='grpc', version=grpc.__version__)

    try:
        for name, version in cls.VERSIONS.items():
            reply.versions.add(name=name, version=version)
    except AttributeError as error:
        pass

    return reply

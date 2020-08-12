# General cogment error
class Error(Exception):
    def __init__(self, msg):
        super().__init__(msg)

class InvalidRequestError(Error):
    def __init__(self, message, request):
        self.request = request
        super().__init__(message)


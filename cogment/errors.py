# General cogment error
class Error(Exception):
    def __init__(self, msg):
        super().__init__(msg)

class InvalidRequestError(Error):
    def __init__(self, message, request):
        self.request = req
        super().__init__(message)


# General cogment error
class Error(Exception):
    pass


# Error that occured while configuring cogment
class ConfigError(Error):
    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

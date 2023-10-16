import logging

logger = logging.getLogger(__name__)


class MainModel(object):
    def __init__(self):

        self.settings = SettingsModel(self)



class SettingsModel(object):
    """
    This class contains a list model parameters which need to be retained when closing dicomfix.
    """

    def __init__(self, model):
        """
        """
        pass

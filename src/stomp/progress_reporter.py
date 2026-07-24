class ProgressReporter:
    '''Class for reporting progress to the user.'''
    enabled: bool = True

    @classmethod
    def begin(cls, text: str):
        '''Start a progress region.'''
        if cls.enabled:
            print(text + "\r", end="")

    @classmethod
    def end(cls):
        '''End the current progress region.'''
        if cls.enabled:
            print("\r\033[K", end="")

class ProgressReporter:
    '''Class for reporting progress to the user.'''

    # Is progress report enabled?
    enabled: bool = True

    # Are we allowed to print ANSI escape sequences?
    ansi_escape: bool = True

    @classmethod
    def begin(cls, text: str):
        '''Start a progress region.'''
        if cls.enabled:
            if cls.ansi_escape:
                print(text + "\r", end="")
            else:
                print(text)
                
    @classmethod
    def end(cls):
        '''End the current progress region.'''
        if cls.enabled and cls.ansi_escape:
            print("\r\033[K", end="")

# SPDX-License-Identifier: BSD-3-Clause

class ProgressReporter:
    '''Class for reporting progress to the user.'''

    # Is progress report enabled?
    enabled: bool = True

    @classmethod
    def begin(cls, text: str):
        '''Start a progress region.'''
        if cls.enabled:
            if len(text) > 70:
                text = text[:35] + " ... " + text[-35:]
            print(text + "\r", end="")
                
    @classmethod
    def end(cls):
        '''End the current progress region.'''
        if cls.enabled:
            print("\r\033[K", end="")

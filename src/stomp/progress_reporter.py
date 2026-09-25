# SPDX-License-Identifier: BSD-3-Clause

class ProgressReporter:
    '''Class for reporting progress to the user.'''

    # Is progress report enabled?
    enabled: bool = True

    # Count of number of progress messages
    count: int = 0

    @classmethod
    def begin(cls, text: str):
        '''Start a progress region.'''
        if cls.enabled:
            if len(text) > 60:
                text = text[:30] + " ... " + text[-30:]
            print(f"[{cls.count}] " + text + "\r", end="")
            cls.count += 1
                
    @classmethod
    def end(cls):
        '''End the current progress region.'''
        if cls.enabled:
            print("\r\033[K", end="")

# SPDX-License-Identifier: BSD-3-Clause

'''This module supports emitting coloured text on the console.'''


class Colour:
    '''Colour codes for colourful text.'''
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    AMBER = '\033[38;2;255;191;0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    ENDC = '\033[0m'

    # Is colour enabled?
    enabled: bool = True

    @classmethod
    def colour(cls, colour: str, text: str):
        if cls.enabled:
           return colour + text + cls.ENDC
        else:
           return text

    @classmethod
    def blue(cls, text: str):
        return cls.colour(cls.BLUE, text)

    @classmethod
    def cyan(cls, text: str):
        return cls.colour(cls.CYAN, text)

    @classmethod
    def green(cls, text: str):
        return cls.colour(cls.GREEN, text)

    @classmethod
    def red(cls, text: str):
        return cls.colour(cls.RED, text)

    @classmethod
    def amber(cls, text: str):
        return cls.colour(cls.AMBER, text)

    @classmethod
    def bold(cls, text: str):
        return cls.colour(cls.BOLD, text)

    @classmethod
    def underline(cls, text: str):
        return cls.colour(cls.UNDERLINE, text)

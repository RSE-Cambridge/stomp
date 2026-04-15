# SPDX-License-Identifier: BSD-3-Clause

'''This module supports emitting coloured text on the console.'''


class Colour:
    '''Colour codes for colourful text.'''
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    ENDC = '\033[0m'


def blue(text: str):
    return Colour.BLUE + text + Colour.ENDC


def cyan(text: str):
    return Colour.CYAN + text + Colour.ENDC


def green(text: str):
    return Colour.GREEN + text + Colour.ENDC


def red(text: str):
    return Colour.RED + text + Colour.ENDC


def bold(text: str):
    return Colour.BOLD + text + Colour.ENDC


def underline(text: str):
    return Colour.UNDERLINE + text + Colour.ENDC

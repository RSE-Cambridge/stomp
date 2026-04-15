'''This module provides a small set of parser combinators.'''

# Class for parse errors
# ======================


# Class for parse errors
class ParseError(Exception):
    def __init__(self, txt=None, pos=None):
        # Character position of error
        self.pos = pos
        # Text being parsed
        self.txt = txt

# Primitive parsers
# =================


def empty(x):
    '''Consume nothing and return given value'''
    def parse(txt, pos):
        return (x, pos)
    return parse


def char(pred=lambda x: True):
    '''Consume any character that satisfies the given predicate'''
    def parse(txt, pos):
        if pos < len(txt):
            c = txt[pos]
            if pred(c):
                pos += 1
                return (c, pos)
        return ParseError(txt, pos)
    return parse


def space():
    '''Consume as much whitespace as possible'''
    def parse(txt, pos):
        while pos < len(txt):
            if not txt[pos].isspace():
                return (None, pos)
            pos += 1
        return (None, pos)
    return parse


def consume(s):
    '''Consume given string'''
    def parse(txt, pos):
        end = pos + len(s)
        if txt[pos:end] == s:
            return (s, end)
        return ParseError(txt, pos)
    return parse


# Primitive combinators
# =====================


def chain(*parsers):
    '''Chain a list of parsers, one after the other, to form a new parser'''
    def parse(txt, pos):
        results = []
        for p in parsers:
            result = p(txt, pos)
            if isinstance(result, ParseError):
                return result
            pos = result[1]
            results.append(result[0])
        return (results, pos)
    return parse


def attempt(p):
    '''Attempt given parser and backtrack if it fails'''
    def parse(txt, pos):
        result = p(txt, pos)
        if not isinstance(result, ParseError):
            return result
        return ParseError(txt, pos)
    return parse


def choice(*parsers):
    '''Choice of parsers without backtracking'''
    def parse(txt, pos):
        for p in parsers:
            result = p(txt, pos)
            if isinstance(result, ParseError):
                if result.pos != pos:
                    return result
            else:
                return result
        return ParseError(txt, pos)
    return parse


def lift(f, *parsers):
    '''Apply given function to results of given parsers'''
    def parse(txt, pos):
        result = chain(*parsers)(txt, pos)
        if isinstance(result, ParseError):
            return result
        else:
            return (f(*result[0]), result[1])
    return parse


def many(p, at_least=0):
    '''Apply the given parser as many times as possible'''
    def parse(txt, pos):
        results = []
        while True:
            result = p(txt, pos)
            if isinstance(result, ParseError):
                if result.pos != pos:
                    return result
                elif len(results) >= at_least:
                    return (results, pos)
                else:
                    return result
            results.append(result[0])
            pos = result[1]
    return parse

# Composite parsers
# =================


def token(s):
    '''Consume given string and any trailing whitespace'''
    return lift(lambda x, _: x,
                consume(s),
                space())


def optional(p):
    '''Make given parser optional'''
    return choice(p, empty(None))


def many1(p):
    '''Apply the given parser at least once and as many times as possible'''
    return many(p, at_least=1)


def sepby1(sep, p):
    '''Apply parser at least once and as many times as possible, with
    separator in between'''
    return lift(lambda first, rest: [first] + rest,
                p,
                many(lift(lambda _, x: x, sep, p)))


def sepby(sep, p):
    '''Apply parser as many times as possible, with separator in between'''
    return choice(sepby1(sep, p), empty([]))


def natural():
    '''Consume a non-negative integer'''
    return lift(lambda digits, _: int("".join(digits)),
                many1(char(lambda x: x.isdigit())),
                space())

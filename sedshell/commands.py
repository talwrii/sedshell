import abc
import re

class Command(object):
    "An interface to process lines"
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def handle_line(self, terminal, line):
        "Process a line of input. Return False if we haven't finished with the line"
        return True

    @abc.abstractmethod
    def done_processing(self):
        "Return True if this command should be replaced by another"
        return True

    @classmethod
    def from_function(cls, func):
        "Create a simple command that reads one line and processes it"
        # This should probably do some sort of interning...
        #   I'm not sure if classes garbage collect
        #   well
        class FunctionCommand(cls):
            def handle_line(self, terminal, line):
                return func(terminal, line)

            def done_processing(self):
                return True
        FunctionCommand.name = func.__name__
        FunctionCommand.doc  = func.__doc__
        return FunctionCommand
class SkipWhileCommand(Command):
    name = 'skip_while'
    doc = 'Skip entries until a regular expression stops matching'

    def __init__(self):
        Command.__init__(self)
        self._regex = None
        self._finished = False

    def handle_line(self, terminal, line):
        if self._regex is None:
            self._regex = prompt('Regex:', terminal)

        if not re.search(self._regex, line, re.IGNORECASE):
            LOGGER.debug('Finished skipping')
            terminal.write('\n')
            self._finished = True
            return False
        else:
            return True

    def done_processing(self):
        return self._finished


class SkipUntilCommand(Command):
    name = 'skip_until'
    doc = 'Skip entries until a regular expression matches'

    def __init__(self):
        Command.__init__(self)
        self._regex = None
        self._finished = False

    def handle_line(self, terminal, line):
        if self._regex is None:
            self._regex = prompt('Regex:', terminal)

        if re.search(self._regex, line, re.IGNORECASE):
            LOGGER.debug('Finished skipping')
            terminal.write('\n')
            self._finished = True
            return False
        else:
            return True

    def done_processing(self):
        return self._finished



import logging
import threading
import unittest

import queue

LOGGER = logging.getLogger('test_pipe')

class Symbol(object):
    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return 'Symbol({!r})'.format(self._name)

    def __eq__(self, other):
        if isinstance(other, Symbol):
            return self._name == other._name
        else:
            return False

CLOSE = Symbol('close')

def bipipe(name=None):
    "Create a pair of bi-directional pipes"
    twin1 = Pipe(name + ' end 1')
    twin2 = Pipe(name + ' end 2')
    return BidirectionalPipe(twin1, twin2), BidirectionalPipe(twin2, twin1)

class BidirectionalPipe(object):
    "Join two pipes into a bidirectional pipe"
    def __init__(self, pipe1, pipe2):
        self._pipe1 = pipe1
        self._pipe2 = pipe2

    def write(self, text):
        return self._pipe2.write(text)

    def close(self):
        return self._pipe2.close()

    def readline(self):
        return self._pipe1.readline()

    def readchar(self):
        return self._pipe1.readchar()

    def flush(self):
        pass

class Pipe(object):
    "A blocking file-like object used for testing"
    def __init__(self, name=None):
        self.closed = False
        self._buffer = []
        self._lock = threading.Lock()
        self._event = queue.Queue() # This implies one reader and one writer
        self._name = name

    def __repr__(self):
        return '<Pipe {}>'.format(self._name or id(self))

    def write(self, text):
        with self._lock:
            #LOGGER.debug('%r Writing %r', self, text)
            self._buffer.append(text)
            LOGGER.debug('%r Notifying', self)
            self._event.put(True)

    def flush(self):
        pass

    def readchar(self):
        LOGGER.debug('%r Reading character', self)
        while True:
            with self._lock:
                if self._buffer:
                    if self._buffer[0] == CLOSE:
                        return ''
                    else:
                        part = self._buffer.pop(0)
                        if part[1:]:
                            self._buffer.insert(0, part[1:])
                        c = part[:1]
                        if c:
                            LOGGER.debug('%r read character %r', self, c)
                            return c
                        else:
                            continue
            self._event.get()

    def readline(self):
        line_parts = []
        line_terminator = None
        while line_terminator is None:
            new_parts, line_terminator = self._read_line_parts()
            LOGGER.debug('%r new parts %r, %r', self, new_parts, line_terminator)
            line_parts.extend(new_parts)
            if line_terminator is not None:
                result = ''.join(line_parts) + line_terminator
                LOGGER.debug('%r Read line %r', self, result)
                return result
            else:
                LOGGER.debug('%r Waiting for more data', self)
                if self.closed:
                    continue
                else:
                    self._event.get()
                    continue

    def _read_line_parts(self):
        "Read bits of the line as they are written, say if the line was closed"
        line_parts = []
        while True:
            with self._lock:
                if not self._buffer:
                    return line_parts, None

                part = self._buffer.pop(0)
                LOGGER.debug('New part %r', part)

                if part == CLOSE:
                    LOGGER.debug('%r closing', self)
                    self.closed = True
                    return line_parts, ''

                first, sep, second = part.partition('\n')
                line_parts.append(first)

                if sep:
                    self._buffer.insert(0, second)
                    return line_parts, '\n'

    def close(self):
        with self._lock:
            self.closed = True
        self.write(CLOSE)


class TestPipe(unittest.TestCase):
    def test_readline(self):
        pipe = Pipe()
        pipe.write('one\ntwo\n')
        pipe.close()
        self.assertEquals(pipe.readline(), 'one\n')
        self.assertEquals(pipe.readline(), 'two\n')
        self.assertEquals(pipe.readline(), '')

    def test_readchar(self):
        pipe = Pipe()
        pipe.write('12')
        self.assertEquals(pipe.readchar(), '1')
        self.assertEquals(pipe.readchar(), '2')

        pipe.write('3')
        pipe.write('4')

        self.assertEquals(pipe.readchar(), '3')
        self.assertEquals(pipe.readchar(), '4')



if __name__ == '__main__':
    #logging.basicConfig(level=logging.DEBUG)
    unittest.main()

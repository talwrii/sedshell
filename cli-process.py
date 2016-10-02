#!/usr/bin/python

import abc
import argparse
import contextlib
import json
import logging
import os
import re
import select
import shutil
import string
import subprocess
import sys
import tempfile
import threading
import time
import tty
import unittest

import fasteners
import readchar

import termios
import test_pipe

LOGGER = logging.getLogger()

HERE = os.path.dirname(__file__) or '.'
WRITER = os.path.join(HERE, 'write-to-file.py')

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

def readchar(stream, wait_for_char=True):
    if hasattr(stream, 'readchar'):
        return stream.readchar()

    old_settings = termios.tcgetattr(stream)
    tty.setcbreak(stream.fileno())
    try:
        if wait_for_char or select.select([stream, ], [], [], 0.0)[0]:
            char = os.read(stream.fileno(), 1)
            return char if type(char) is str else char.decode()
    finally:
        termios.tcsetattr(stream, termios.TCSADRAIN, old_settings)

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()


DATA_LOCK = threading.Lock()
@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        with DATA_LOCK:
            data = read_json(data_file)
            yield data

            output = json.dumps(data)
            with open(data_file, 'w') as stream:
                stream.write(output)

def menu(commands):
    "String describing possible actions"
    result = []
    for key, command in sorted(commands.items()):
        result.append('{} - {}'.format(format_key(key), command.doc))
    return '\n' + '\n'.join(result) + '\n\n'

def format_key(key):
    if ord(key) <= 26:
        return 'C-' + string.letters[ord(key) - 1] # my keyboard doesn't have a null character
    elif key == ' ':
        return 'SPACE'
    else:
        return key

class ShellRunner(object):
    def __init__(self, store):
        self._history = []
        self._store = store

    def _read_command(self, terminal, consume):
        terminal.write('Command:\n')
        command = terminal.readline().strip()

        self._history.append((command, consume))
        return command

    def run(self, terminal, line):
        "Run a shell command on the line"
        command = self._read_command(terminal, consume=True)
        succeeded = run_command(command, line)
        return succeeded

    def skip(self, terminal, line):
        "Skip this line"
        del terminal, line
        return True

    def run_no_consume(self, terminal, line):
        "Run a shell command, but allow other commands to run"
        command = self._read_command(terminal, consume=False)
        run_command(command, line)
        return False

    def repeat(self, terminal, line):
        "Repeat the last command"
        del terminal
        command, consume = self._history[-1]
        succeeded = run_command(command, line)
        return consume and succeeded

    def run_raw(self, terminal, line):
        "Run a command and print output (ignoring line)"
        del line

        terminal.write('Command:\n')
        command = terminal.readline().strip()

        p = subprocess.Popen(command, stdin=terminal, shell=True)
        p.wait()

    def run_shell(self, terminal, line):
        "Start an interactive shell"
        del line
        shell = os.environ.get('SHELL', '/bin/bash')
        p = subprocess.Popen([shell, '-i'], stdin=terminal)
        p.wait()
        return False

    def save_last(self, terminal, line):
        "Save the last command to a key"
        del line
        terminal.write('Command letter?\n')
        terminal.flush()
        c = readchar(terminal)

        command, consume = self._history[-1]
        print 'storing', command, consume
        self._store.store(c, command, consume)
        return False

    def exit(self, terminal, line):
        "Exit"
        del terminal, line
        sys.exit()

def run_command(command, line):
    full_command = '{} {}'.format(command, line)
    LOGGER.debug('Running %r', full_command)
    p = subprocess.Popen(full_command, shell=True)
    p.wait()
    return p.returncode == 0

DEFAULT_CONFIG = os.path.join(os.environ['HOME'], '.config', 'cli-process')

PARSER = argparse.ArgumentParser(description='')
PARSER.add_argument('--debug', action='store_true', help='Print debug output')
PARSER.add_argument('--test', action='store_true', help='Print debug output')
PARSER.add_argument('--config-dir', '-C', help='Directory to store configuration and data', default=DEFAULT_CONFIG)

def main():
    args, remaining = PARSER.parse_known_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if args.test:
        sys.argv[1:] = remaining
        unittest.main()
    else:
        print run(sys.argv[1:])

class ShellCommandStore(object):
    def __init__(self, config_dir):
        self._filename = os.path.join(config_dir, 'data.json')

    def store(self, char, command, consume):
        with with_data(self._filename) as data:
            data.setdefault('commands', dict())
            data['commands'][char] = [command, consume]

    def lookup(self, char):
        with with_data(self._filename) as data:
            commands = data.setdefault('commands', dict())
            if char in commands:
                command, consume = commands[char]
                def runner(terminal, line):
                    del terminal
                    run_command(command, line)
                    return consume
                return Command.from_function(runner)
            else:
                return None
    def menu(self):
        result = []
        with with_data(self._filename) as data:
            commands = data.setdefault('commands', dict())
            for char, (command, consume) in sorted(commands.items()):
                execute_char = '!' if consume else '&'
                result.append('{} - {} {}'.format(char, execute_char, command))
        return '\n' + '\n'.join(result) + '\n'


def prompt(prompt_string, terminal):
    terminal.write(prompt_string + '\n')
    return terminal.readline().strip('\n')

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

def run(argv, stdin=None, terminal=None):
    args = PARSER.parse_args(argv)

    stdin = sys.stdin if stdin is None else stdin
    terminal = open('/dev/tty', 'w+') if terminal is None else terminal

    # terminal != stdin if redirecting input
    if not os.path.isdir(args.config_dir):
       os.mkdir(args.config_dir)

    shell_store = ShellCommandStore(args.config_dir)
    shell = ShellRunner(shell_store)

    def show_help(terminal, line):
        "List commands"
        del line
        terminal.write(menu(commands))
        terminal.write(shell_store.menu())
        return False

    commands = {
        '!': Command.from_function(shell.run),
        '&': Command.from_function(shell.run_no_consume),
        '\x04': Command.from_function(shell.exit),
        '^': Command.from_function(shell.repeat),
        '$': Command.from_function(shell.run_shell),
        '>': Command.from_function(shell.save_last),
        '<': Command.from_function(shell.run_raw),
        ' ': Command.from_function(shell.skip),
        '?': Command.from_function(show_help),
        '\\': SkipWhileCommand,
        }

    terminal.write('cli-process\n')
    terminal.write('? - for help. Run with --help for documentation\n\n')

    command = None

    while True:
        LOGGER.debug('mainloop: Reading line')
        line = stdin.readline().strip()
        LOGGER.debug('mainloop: Read line %r', line)
        if line == '':
            break
        else:
            LOGGER.debug('mainloop: Got input %r', line)


        while True:
            terminal.write(line + "\n")
            if command is None or command.done_processing():

                LOGGER.debug('mainloop: Awaiting command for %r', line)
                c = readchar(terminal)
                LOGGER.debug('mainloop: Running command %r for %r', c, line)

                CommandClass = shell_store.lookup(c) or commands.get(c)
                command = CommandClass()

                if command is None:
                    show_help(terminal, line)
                    continue

            LOGGER.debug('mainloop: Running command %r', command.name)
            finished = command.handle_line(terminal, line)
            if finished:
                break

def spawn(f, *args, **kwargs):
	thread = threading.Thread(target=f, args=args, kwargs=kwargs)
	thread.setDaemon(True)
	thread.start()
	return thread

class StupidIpc(object):
    "A stupid form of rpc"
    def __init__(self):
        self.command_file = tempfile.NamedTemporaryFile(delete=False)
        self.seq_file = tempfile.NamedTemporaryFile(delete=False)
        self.set_seq(0)

    def set_seq(self, seq):
        with open(self.seq_file.name, 'w') as stream:
            stream.write(str(seq))

    def await_seq(self, sought_seq):
        # Wait for the other side to confirm that it has
        #  reach sought_seq
        for i in range(7):
            LOGGER.debug('Awaiting sync to %r', sought_seq)
            try:
                data = self.read()
            except ValueError:
                pass
            else:
                if data[0] == str(sought_seq):
                    return data

            time.sleep(0.01 * 2**i) # geometric backoff
        else:
            raise Exception('Timed out waiting for {}'.format(sought_seq))

    def read(self):
        with open(self.command_file.name) as stream:
            lines = stream.readlines()
            if not lines:
                raise ValueError('empty')
            else:
                data = lines[-1]
                return json.loads(data)

    def write_command(self):
        return '{} {} {}\n'.format(WRITER, self.seq_file.name, self.command_file.name)

    def clean_up(self):
        os.unlink(self.command_file.name)
        os.unlink(self.seq_file.name)

class TestProcess(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()
        self.stdin = test_pipe.bipipe(name='stdin')
        self.terminal = test_pipe.bipipe(name='terminal')
        self.ipc = StupidIpc()

    def tearDown(self):
        self.ipc.clean_up()
        shutil.rmtree(self.direc)

    def run_cli(self, *args):
        new_args = ('--config-dir', self.direc) + tuple(args)
        return run(new_args, self.stdin[1], self.terminal[1])

    def test_run(self):
        run_thread = spawn(self.run_cli)
        self.stdin[0].write('hello\n')
        self.stdin[0].close()
        self.terminal[0].write('!')
        self.terminal[0].write(self.ipc.write_command())
        run_thread.join()

        result = self.ipc.read()
        self.assertEquals(result[1], ["hello"])

    def test_dont_run(self):
        "Test & command does not consume"

        run_thread = spawn(self.run_cli)
        self.ipc.set_seq(1)
        self.stdin[0].write('1\n2\n')
        self.stdin[0].close()
        self.terminal[0].write('&')
        self.terminal[0].write(self.ipc.write_command())

        result = self.ipc.await_seq(1)
        self.assertEquals(result[1], ["1"])

        self.ipc.set_seq(2)

        self.terminal[0].write('!')
        self.terminal[0].write(self.ipc.write_command())

        result = self.ipc.await_seq(2)
        # We didn't consume the first line with &
        self.assertEquals(result[1], ["1"])

        self.terminal[0].write('\x04')

        run_thread.join()





    def test_exit(self):
        run_thread = spawn(self.run_cli)
        self.stdin[0].write('hello\nhey\n')
        self.terminal[0].write('\x04')
        run_thread.join(timeout=0.1)
        self.assertFalse(run_thread.isAlive())

    def test_save(self):
        run_thread = spawn(self.run_cli)
        self.stdin[0].write('hello\nhey\n')
        self.stdin[0].close()

        self.ipc.set_seq(1)
        self.terminal[0].write('!')
        self.terminal[0].write(self.ipc.write_command())

        self.ipc.await_seq(1)

        # save the command
        self.terminal[0].write('>')
        self.terminal[0].write('c')


        self.ipc.set_seq(2)
        # make sure it works
        self.terminal[0].write('c')

        self.ipc.await_seq(2)
        run_thread.join()

        result = self.ipc.read()
        self.assertEquals(result[0], '2')



if __name__ == '__main__':
    main()

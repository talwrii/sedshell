#!/usr/bin/python

import argparse
import contextlib
import json
import logging
import os
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
        result.append('{} - {}'.format(format_key(key), command.__doc__))
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

    def last(self):
        return self._history[-1]

    def _read_command(self, terminal):
        command = terminal.readline().strip()
        self._history.append(command)
        return command

    def run(self, terminal, line):
        "Run a shell command"
        terminal.write('Command:\n')
        command = self._read_command(terminal)
        run_command(command, line)
        return True

    def skip(self, terminal, line):
        "Skip this line"
        del terminal, line
        return True

    def run_no_consume(self, terminal, line):
        "Run a shell command, but allow other commands to run"
        self.run(terminal, line)
        return False

    def repeat(self, terminal, line):
        "Repeat the last command"
        del terminal
        command = self._history[-1]
        run_command(command, line)
        return True

    def save_last(self, terminal, line):
        "Save the last command to a key"
        del line
        terminal.write('Command letter?\n')
        terminal.flush()
        c = readchar(terminal)
        self._store.store(c, self.last())
        return False

    def exit(self, terminal, line):
        "Exit"
        del terminal, line
        sys.exit()

def run_command(command, line):
    full_command = '{} {}'.format(command, line)
    LOGGER.debug('Running %r', full_command)
    subprocess.check_call(full_command, shell=True)

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

    def store(self, char, command):
        with with_data(self._filename) as data:
            data.setdefault('commands', dict())
            data['commands'][char] = command

    def lookup(self, char):
        with with_data(self._filename) as data:
            commands = data.setdefault('commands', dict())
            if char in commands:
                command = commands[char]
                def runner(terminal, line):
                    del terminal
                    run_command(command, line)
                    return True
                return runner
            else:
                return None

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
        return False

    commands = {
        '!': shell.run,
        '&': shell.run_no_consume,
        '\x04': shell.exit,
        '^': shell.repeat,
        '>': shell.save_last,
        ' ': shell.skip,
        '?': show_help,
        }

    terminal.write('cli-process\n')
    terminal.write('? - for help. Run with --help for documentation\n\n')

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
            LOGGER.debug('mainloop: Awaiting command for %r', line)
            c = readchar(terminal)
            LOGGER.debug('mainloop: Running command %r for %r', c, line)

            command = shell_store.lookup(c) or commands[c]
            LOGGER.debug('mainloop: Running command %r', command.__name__)
            finished = command(terminal, line)
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

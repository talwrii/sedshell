import json
import logging
import os
import shutil
import tempfile
import threading
import time
import unittest

from sedshell import sedshell, test_pipe

LOGGER = logging.getLogger('test')

HERE = os.path.dirname(__file__) or '.'
WRITER = os.path.join(HERE, 'write-to-file.py')


def spawn(f, *args, **kwargs):
	thread = threading.Thread(target=f, args=args, kwargs=kwargs)
	thread.setDaemon(True)
	thread.start()
	return thread



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
        return sedshell.run(new_args, self.stdin[1], self.terminal[1])

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

if __name__ == '__main__':
    unittest.main()

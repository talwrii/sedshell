#!/usr/bin/python
import sys
import json

seq_file = sys.argv[1]
output_file = sys.argv[2]
args = sys.argv[3:]
with open(seq_file) as stream:
     sequence = stream.read() # Allow for synchronization

with open(output_file, 'a') as stream:
    stream.write('\n')
    stream.write(json.dumps([sequence, args]))

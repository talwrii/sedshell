# sedshell

An interactive, interactively-extensible, command-line tool to do things to a stream of lines. The prototypical use case is running commands on files based on user input

## Example

Compressing, leaving, or deleting pictures.

```bash
$ find /tmp/things | sedshell
sedshell
? - for help. Run with --help for documentation

/tmp/things <--- PRESSED SPACE TO SKIP
/tmp/things/rubbish1.jpg <---- PRESSED "!" TO RUN SOMETHING
Command:
rm
/tmp/things/rubbish2 <----- PRESSED ">" TO SAVE COMMAND
Command letter? <---- PRESSED "d" TO SAVE d key
/tmp/things/rubbish2 <---- PRESSED "d"
/tmp/things/rubbish3.jpg <----- PRESSED "d"
/tmp/things/big-scan-on-contract1.jpg <----- PRESSED "!"
Command:
gzip
/tmp/things/big-scan-of-contract2.jpg <---- PRESSED ">"
Command letter? <----- PRESSED "z"
/tmp/things/big-scan-of-contract2.jpg <---- PRESSED "z"
/tmp/things/send-to-dave.jpg <----- PRESSED SPACE
/tmp/things/send-to-lucy.jpg <----- PRESSED SPACE
```

The saved command will be remembered the next time `sedshell` runs.

## Motivation

Going through a list of things and doing things based on a human decision is something I do quite a lot. Doing this often involves tedious repetition, but often the task can't really be automated, and each time you automate part of it you find special cases.

Some examples: going through email, triaging bugs, filing things, adding changes to a git repository, reviewing code, approving requests, screening, reverting git changes.

I have found myself writing ad-hoc tools for this purpose, and some such tools are in common use such as `git add -p`.

This tool seeks to provide something general for this sort of task: an interactive, user modifiable map command.

## Philosophy

Do one thing well... but also be turing-complete.

## Tips

If you find something is impossible to achieve from within the program for a given line, then you can use the '$' to start an interactive shell.

## Possible features

* A *display command* which could be automatically run when each line arrives
* Sets of common actions that can be be enabled from the shell, for example URL- or file-based actions.
* Namespaces for commands, and actions to modify these namespaces, e.g `sedshell photos` veruss `sedshell blogposts`
* Forward and back commands.
* Inplace operation for large lists where each file cannot be processed.
* Python rather than shell functions
* Shell templates (like `xargs -I`) for repeating arguments, and if the line shouldn't be the last argument
* Perhaps support `json` input like `recordstream`

## Developing

There are some tests, run them:

```bash
python setup.py develop
python test.py
```

The tests are very blackbox, they test the program as a whole. for this tool this approach works well in that it allows aggressive refactoring, and the program is simple enough that this doesn't mask edge-cases.

Coverage is shoddy: a privilege for the project's author. If you send me a pull request I'm going to make you write tests for your features with full coverage :P.

## Installing

```bash
python setup.py install
sedshell
```

## Similar tools

I could not really find any direct analogues, however `vifm` in some way has a similar philosophy. Predictable tasks can be achieved with `xargs`.

#!/usr/bin/python
#
#  TimeTracker
#
#  Keep track of timers.  Only one timer is ever running at a time.
#  When run with no arguments print a report.
#  When run with position arguments, create a new timer with the arguments as
#  the name.  If there is more than 1 positional argument, they are combined
#  with spaces to make 1 name.
#  There is no real connection of one timer to the other, except that reports
#  will combine timers with the same name in some way.
#  As a convenience, a name specificed on the command line will be resolved
#  through the following steps:
#    1) look in a map of names to names, and use that mapped name
#    2) do a regular expression search starting with the most recent timer and
#       use the first match as the name
#    3) use the name as is
#  Maps are created with the -map option.  The argument to map should be a
#  single argument, and all remaining positional arguments are what it maps
#  too.  This could be used to make convenient indexes.
#
#  USAGE
#
#  tt
#    generated a report.  Various options control the type of report.
#
#  tt [-e|--explicit] name 
#    1. Stop any current timer.
#    2. Resolve name (unless -e).  Combine all positional arguments into a
#       single, space separated name. (It is ok to use quotes on the command
#       line to create a single argument.  Of course, the command line goes
#       through any usual shell parsing.)  That name is resolved into the final
#       timer name through the following steps:
#         1) look in a map of names to names, and use that mapped name
#         2) do a regular expression search starting with the most recent timer
#            and use the first match as the name
#         3) use the name as is
#       Note that "." will match the most recent timer.
#    3. Start a new timer with this name.
#     
#  tt -stop   
#    Stop any current timer.
#
#  tt --map "map from name"  map to name
#    Create a map from one name to another.  The first name must be in quotes
#    because it is an argument to the option.  The "map to name" goes through
#    the usual name lookup too.  If the "map to name" is empty, the map is
#    deleted.  Typical example might be to map indexes to full names. 
#
#  tt --rename name
#    Rename the last timer.  Just in case you made a minor mistake in the last
#    task.  TODO:  Ideally you could make arbitrary changes to the timers.  I
#    would probably do that by just making the save file trivial to edit.
#
#  tt --check name
#    If you want to check what name would get used with the given arguments.
#
#  IMPLEMENTATION
#
#  There are only two data structures.
#  1. dictionary/map of name to name
#  2. array of timers
#     - record start time, end time, and name
#      - tuple of (string, datetime, datetime)
#  3. TODO: an array to archive older timers so they aren't include in reports
#     or searches
#  
#  Basic operation:
#  1. read file of map and timers
#  2. parse and handle arguments
#     - print a report when no options or arguments
#     - start new timer when just name arguments
#     - handle special options
#  3. save file
#

import os
import datetime
import re
import pickle
import optparse


parser = optparse.OptionParser()
parser.add_option("-f", "--file",
                  dest="filename", default="~/.timetracker", metavar="FILE",
                  help="Use FILE for time tracker data")
parser.add_option("-q", "--quiet",
                  action="store_false", dest="verbose", default=True,
                  help="don't print status messages to stdout")
parser.add_option("-e", "--explicit",
                  action="store_true", dest="explicit", default=False,
                  help="Use this name explicitly, don't use map or search")
parser.add_option("-m", "--map",
                  dest="mapname", metavar="NAME",
                  help="Map NAME to a name from the positional arguments")
parser.add_option("-s", "--stop",
                  action="store_true", dest="stop", default=False,
                  help="Stop any current timer.")
parser.add_option("-r", "--rename",
                  action="store_true", dest="rename", default=False,
                  help="Rename the last timer")
parser.add_option("-c", "--check",
                  action="store_true", dest="check", default=False,
                  help="Check what the name resolves to.  Don't make any changes")

(options, args) = parser.parse_args()
print options

name_map = {}
timers = []
save_changes = False
now = datetime.datetime.now() # Assume we'll need it, so get it once.


def main():
    fname = os.path.expanduser(options.filename)
    if os.path.exists(fname):
        load(fname)
    name = None
    if args:
        name = resolve_name(" ".join(args))
    if options.stop:
        stop_timer()
    elif options.mapname:
        handle_map(options.mapname, name)
    elif options.rename:
        rename_last_timer(name)
    elif options.check:
        print "from:", " ".join(args)
        print "to:  ", name
    elif name:
        stop_timer()
        start_timer(name)
    else:
        report()
    global save_changes
    if save_changes:
        save(fname)

def load(fname):
    global name_map, timers
    if options.verbose:
        print "loading", fname
    with open(fname, "rb") as f:
        name_map = pickle.load(f)
        timers = pickle.load(f)
        if options.verbose:
            print "loaded", len(name_map), "maps,", len(timers), "timers"

def save(fname):
    if options.verbose:
        print "Saving", fname
    with open(fname, "wb") as f:
        pickle.dump(name_map, f, protocol=2)
        pickle.dump(timers, f, protocol=2)
        if options.verbose:
            print "saved", len(name_map), "maps,", len(timers), "timers"

def resolve_name(name):
    if not options.explicit:
        if name in name_map:
            name = name_map[name]
            if options.check:
                print "check: name in map"
        else:
            # TODO:  Hmm, this would get slow if there were too many.  But I
            # assume even with thousands it would not be noticable.  Could at
            # least add a command to archive old timers.
            for t in reversed(timers):
                if re.search(name, t[0]):
                    name = t[0]
                    if options.check:
                        print "check: name matches existing timer"
                    break;
    if options.verbose:
        print "Using name:", name
    return name

def handle_map(from_name, to_name):
    global save_changes, name_map
    if to_name:
        name_map[from_map] = to_name
        save_changes = True
    elif from_name in name_map:
        del name_map[from_name]
        save_changes = True
    else:
        print "Map not changed!"

def rename_last_timer(name):
    global save_changes, timers
    if len(timers) > 0:
        t = timers[-1]
        old_name = t[0]
        timers[-1] = (name, t[1], t[2])
        save_changes = True
        if options.verbose:
            print "Rename last timer:"
            print "from:", old_name
            print "to:  ", name

def stop_timer():
    global save_changes, timers
    # Stop current timer if it was running
    if len(timers) > 0 and timers[-1][2] == None:
        t = timers[-1]
        timers[-1] = (t[0], t[1], now)
        save_changes = True
        if options.verbose:
            print "Stop", timers[-1][0], now - timers[-1][1]

def start_timer(name):
    global save_changes, timers
    t = (name, now, None)
    timers.append(t)
    save_changes = True
    if options.verbose:
        print "Start", name, now

def report():
    # Print a report
    # Currently prints timers ordered by name and include a total.
    # First, collect all timers in a dictionary by name
    by_name = {}
    for t in timers:
        if t[2] == None:
            t = (t[0], t[1], now)
        if t[0] in by_name:
            by_name[t[0]].append(t)
        else:
            by_name[t[0]] = [t];
    # Second, print timers by name, and a total duration
    for n in by_name:
        print n
        total = datetime.timedelta(0)
        for t in by_name[n]:
            dur = t[2] - t[1]
            print t[1], dur
            total = total + dur
        print "total", total

main()

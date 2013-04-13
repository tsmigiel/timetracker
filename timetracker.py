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
#	1) look in a map of names to names, and use that mapped name
#	2) do a regular expression search starting with the most recent timer and
#	   use the first match as the name
#	3) use the name as is
#  Maps are created with the -map option.  The argument to map should be a
#  single argument, and all remaining positional arguments are what it maps
#  too.  This could be used to make convenient indexes.
#
#  USAGE
#
#  tt
#	generated a report.  Various options control the type of report.
#
#  tt [-e|--explicit] name 
#	1. Stop any current timer.
#	2. Resolve name (unless -e).  Combine all positional arguments into a
#	   single, space separated name. (It is ok to use quotes on the command
#	   line to create a single argument.  Of course, the command line goes
#	   through any usual shell parsing.)  That name is resolved into the final
#	   timer name through the following steps:
#		 1) look in a map of names to names, and use that mapped name
#		 2) do a regular expression search starting with the most recent timer
#			and use the first match as the name
#		 3) use the name as is
#	   Note that "." will match the most recent timer.
#	3. Start a new timer with this name.
#	 
#  tt -stop   
#	Stop any current timer.
#
#  tt --map "map from name"  map to name
#	Create a map from one name to another.  The first name must be in quotes
#	because it is an argument to the option.  The "map to name" goes through
#	the usual name lookup too.  If the "map to name" is empty, the map is
#	deleted.  Typical example might be to map indexes to full names. 
#
#
#  IMPLEMENTATION
#
#  There are only two data structures.
#  1. dictionary/map of name to name
#  2. array of timers
#	 - record start time, end time, and name
#	  - tuple of (string, datetime, datetime)
#  3. TODO: an array to archive older timers so they aren't include in reports
#	 or searches
#  
#  Basic operation:
#  1. read file of map and timers
#  2. parse and handle arguments
#	 - print a report when no options or arguments
#	 - start new timer when just name arguments
#	 - handle special options
#  3. save file
#

import sys
import os
import re
import calendar
import datetime
import pickle
import optparse


parser = optparse.OptionParser(usage="usage: %prog [options] name...")
parser.add_option("-f", "--file",
				  dest="filename", default="~/.timetracker", metavar="FILE",
				  help="use FILE for time tracker data")
parser.add_option("-v", "--verbose",
				  action="store_true", dest="verbose", default=False,
				  help="don't print status messages to stdout")
parser.add_option("-e", "--explicit",
				  action="store_true", dest="explicit", default=False,
				  help="use this name explicitly, don't use map or search")
parser.add_option("-m", "--map",
				  dest="mapname", metavar="NAME",
				  help="map NAME to a name from the positional arguments")
parser.add_option("-s", "--stop",
				  action="store_true", dest="stop", default=False,
				  help="stop any current timer")

(options, args) = parser.parse_args()

# TODO: Hmm, it's convenient to use globals, but should I not use them? I was
# trying to avoid creating a class, but that might be the best solution. 
# One nasty requirement of globals is having to declare them as global in
# functions, which leads to non-obvious errors when you don't.

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
	elif name:
		stop_timer()
		start_timer(name)
	else:
		report()
	if save_changes:
		save(fname)

def date_from_str(str):
	if str == 'None':
		return None
	return datetime.datetime.strptime(str, '%Y-%m-%d %H:%M:%S')

def date_to_str(date):
	if date == None:
		return "None"
	return '{:%Y-%m-%d %H:%M:%S}'.format(date)

def load(fname):
	global name_map, timers
	if options.verbose:
		print "loading", fname
	with open(fname, "rb") as f:
		for line in f:
			field = line.strip().split('\t')
			if field[0] == 'MAP':
				name_map[field[1]] = field[2]
			elif field[0] == 'TIMER':
				start = date_from_str(field[2])
				stop = date_from_str(field[3])
				timers.append((field[1], start, stop))
		if options.verbose:
			print "loaded", len(name_map), "maps,", len(timers), "timers"

def save(fname):
	if options.verbose:
		print "Saving", fname
	with open(fname, "wb") as f:
		for n in name_map:
			f.write('MAP\t{}\t{}\n'.format(n, name_map[n]))
		for t in timers:
			start = date_to_str(t[1])
			stop = date_to_str(t[2])
			f.write('TIMER\t{}\t{}\t{}\n'.format(t[0], start, stop))
		if options.verbose:
			print "saved", len(name_map), "maps,", len(timers), "timers"

def resolve_name(name):
	if not options.explicit:
		if name in name_map:
			name = name_map[name]
			if options.verbose:
				print "name in map"
		else:
			# TODO:  Hmm, this would get slow if there are too many.  But I
			# assume even with thousands it would not be noticable.  Could at
			# least add a command to archive old timers.
			for t in reversed(timers):
				if re.search(name, t[0]):
					name = t[0]
					if options.verbose:
						print "name matches existing timer"
					break;
	if options.verbose:
		print "Using name:", name
	return name

def handle_map(from_name, to_name):
	global save_changes, name_map
	if to_name:
		name_map[from_name] = to_name
		save_changes = True
	elif from_name in name_map:
		del name_map[from_name]
		save_changes = True
	else:
		print "Map not changed!"

def timer_active(t):
	return t[2] == None

def stop_timer():
	global save_changes, timers
	# Stop current timer if it was running
	if len(timers) > 0 and timer_active(timers[-1]):
		t = timers[-1]
		timers[-1] = (t[0], t[1], now)
		save_changes = True
		print "Stop", timers[-1][0], now - timers[-1][1]

def start_timer(name):
	global save_changes, timers
	t = (name, now, None)
	timers.append(t)
	save_changes = True
	print "Start", name, now

def timer_duration(t):
	if timer_active(t):
		dur = now - t[1]
	else:
		dur = t[2] - t[1]
	return dur

def map_str(map, n):
	if n in map:
		return '({})'.format(map[n])
	else:
		return ''

def same_month(prev_date, date):
	 return (prev_date and prev_date.year == date.year
					   and prev_date.month == date.month)
		
def print_month_header(date):
	# calendar.setfirstweekday(calendar.SUNDAY)
	# monthrange doesn't pay attention to firstweekday, the default is MONDAY.
	(firstday, days) = calendar.monthrange(date.year, date.month)
	firstday = (firstday + 1) % 7
	week = "SMTWTFS"
	daytop = "         1111111111222222222233"
	daybot = "1234567890123456789012345678901"
	numweeks = (firstday + days + 6) / 7
	print ' ' * 7, week * numweeks
	print '  {:5.5} {:>{}}'.format(date.strftime("%Y"), daytop[0:days], firstday+days)
	print '  {:5.5} {:>{}}'.format(date.strftime("%B"), daybot[0:days], firstday+days)
	return firstday

def report():
	# Print a report
	# Currently prints timers ordered by name and include a total.
	# First, collect all timers in a dictionary by name
	by_name = {}
	name_order = []
	reverse_name_map = {}
	for n in name_map:
		reverse_name_map[name_map[n]] = n
	for t in timers:
		if t[0] in by_name:
			by_name[t[0]].append(t)
		else:
			by_name[t[0]] = [t];
			name_order.append(t[0])
	# Second, print timers by name, and a total duration
	for n in name_order:
		if n in reverse_name_map:
			print '{} ({})'.format(n, reverse_name_map[n])
		else:
			print n
		total = datetime.timedelta(0)
		for t in by_name[n]:
			dur = timer_duration(t)
			if timer_active(t):
				print "*", t[1], dur
			else:
				print " ", t[1], dur
			total = total + dur
		print "  total", total
	hours = [ "12am", " 1am", " 2am", " 3am", " 4am", " 5am",
			  " 6am", " 7am", " 8am", " 9am", "10am", "11am",
			  "noon", " 1pm", " 2pm", " 3pm", " 4pm", " 5pm",
			  " 6pm", " 7pm", " 8pm", " 9pm", "10pm", "11pm"]
	for n in name_order:
		print '{} {}'.format(n, map_str(reverse_name_map, n))
		prev_date = None
		total = datetime.timedelta(0)
		min_hour = 24
		max_hour = 0
		graph = [[0 for i in range(24)] for j in range(31)]
		for t in by_name[n]:
			start = t[1]
			dur = timer_duration(t)
			if not same_month(prev_date, start):
				indent = print_month_header(start)
				prev_date = start
			inc = 60 - start.minute
			minutes = dur.days * 24 * 60 + (dur.seconds + 59) / 60
			hour = start.hour
			day = start.day
			while minutes > inc:
				graph[day][hour] += inc
				minutes = minutes - inc
				inc = 60
				hour += 1
				if hour == 24:
					day += 1
					hour = 0
					min_hour = 0
					max_hour = 23
			graph[day][hour] += minutes
			if start.hour < min_hour:
				min_hour = start.hour
			if hour > max_hour:
				max_hour = hour
		for h in range(min_hour, max_hour+1):
			sys.stdout.write('  {} {}'.format(hours[h], ' ' * indent))
			for d in range(31):
				if graph[d][h] > 0:
					sys.stdout.write(str((graph[d][h] + 9)/ 10))
				else:
					sys.stdout.write(" ")
			print

main()

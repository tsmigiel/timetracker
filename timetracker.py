#!/usr/bin/env python
#
#  TimeTracker
#
#  typical usage:
#    ln -snf /path/to/timetracker.py ~/bin/tt
#    or alias tt="/path/to/timetracker.py"
#    tt  name of a timer [@tag]* [: comment]  # start a timer
#    tt  -l M|--leap M   name...  # start a timer M minutes ago
#    tt  -s|--stop     # stop active timer
#    tt                # prints active timer
#    tt  -r|--report   # prints a report
#    tt  -c|--calendar # a report like a calendar
#
#  Keep track of timers.  Only one timer is ever running at a time.
#  When run with no arguments print the duration of the active timer.
#  When run with position arguments, create a new timer with the arguments as
#  the name.  If there is more than 1 positional argument, they are combined
#  with spaces to make 1 name.  Any word prefixed with @ is a tag which can be
#  used while printing reports.  Each timer can also have a comment which is
#  started with a :.  Comments are not used during name matching.
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
#  tt -s|--stop   
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
#	 - print the active timer when no options or arguments
#	 - start new timer when just name arguments
#	 - handle special options
#  3. save file
#

import sys
import os
import re
import calendar
import datetime
import optparse
import shutil


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
parser.add_option("-r", "--report",
				  action="store_true", dest="report", default=False,
				  help="generate a report")
# TODO: This would be nicer as --report=cal, the above could be --report=list,
# and set the default for --report accordingly. Can also set report default in
# data file.
parser.add_option("-c", "--report-cal",
				  action="store_true", dest="report_cal", default=False,
				  help="generate a report")
parser.add_option("-l", "--leap",
				  dest="leap", metavar="N", type="int",
				  help="Do a quantum leap to N minutes ago and run the command from that time")

(options, args) = parser.parse_args()

# TODO: Hmm, it's convenient to use globals, but should I not use them? I was
# trying to avoid creating a class, but that might be the best solution. 
# One nasty requirement of globals is having to declare them as global in
# functions, which leads to non-obvious errors when you don't.

version = 2
name_map = {}
timers = []
save_changes = False
tag_char = "@"

# Save it, because at least 1 option will change it.
now = datetime.datetime.now().replace(microsecond=0)

class Timer:

	def __init__(self, name, comment, start, end = None):
		self.name = name.strip()
		self.comment = comment.strip()
		self.start = start
		self.end = end
		# Find words that start with tag_char.  include tag_char so it is
		# obvious when used for things like reporting
		s = " ".join([self.name, self.comment])
		pat = re.compile("".join(["(", tag_char, "\w+)"]))
		self.tags = frozenset(pat.findall(s))
		if not self.tags:
			self.tags = frozenset(["No tags"])

	def active(self):
		return self.end == None

	def duration(self):
		if self.active():
			dur = now - self.start
		else:
			dur = self.end - self.start
		return dur


def main():
	global now
	fname = os.path.expanduser(options.filename)
	if os.path.exists(fname):
		load(fname)
	name = None
	if args:
		name, sep, comment = " ".join(args).partition(":")
		name = resolve_name(name)
	if options.leap:
		now = now - datetime.timedelta(seconds = options.leap*60)
	if options.stop:
		stop_timer()
	elif options.mapname:
		handle_map(options.mapname, name)
	elif name:
		stop_timer()
		start_timer(name, comment)
	elif options.report:
		report()
	elif options.report_cal:
		report_cal()
	elif len(timers) > 0 and timers[-1].active():
		d = int(timers[-1].duration().total_seconds() / 60)
		print "{} {:d}:{:02d}".format(timers[-1].name, d / 60, d % 60)
	else:
		print "No active timer"
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
	global name_map, timers, save_changes
	if options.verbose:
		print "loading", fname
	with open(fname, "rb") as f:
		load_version = 0
		for line in f:
			field = line.rstrip('\r\n').split('\t')
			if field[0] == 'MAP':
				name_map[field[1]] = field[2]
			elif field[0] == 'TAGCHAR':
				tag_char = field[1]
			elif field[0] == 'TIMER':
				if load_version > 1:
					start = date_from_str(field[1])
					stop = date_from_str(field[2])
					timers.append(Timer(field[3], field[4], start, stop))
				elif load_version == 1:
					start = date_from_str(field[1])
					stop = date_from_str(field[2])
					timers.append(Timer(field[3], "", start, stop))
				else:
					start = date_from_str(field[2])
					stop = date_from_str(field[3])
					timers.append(Timer(field[1], "", start, stop))
			elif field[0] == 'VERSION':
				load_version = int(field[1])
		if options.verbose:
			print "loaded", len(name_map), "maps,", len(timers), "timers"
	if load_version != version:
		save_changes = True

def backup(fname):
	backup_name = fname + ".bak"
	if os.path.exists(backup_name):
		# if the new file is smaller than the previous back up, assume
		# there was an error and don't overwrite the back up.
		old_stat = os.stat(backup_name)
		new_stat = os.stat(fname)
		if old_stat.st_size > new_stat.st_size:
			print "Abort back up because", backup_name, "is smaller than", fname
			return
	if options.verbose:
		print "Back up", fname, "to", backup_name
	shutil.copyfile(fname, backup_name)

def save(fname):
	if options.verbose:
		print "Saving", fname
	backup(fname)
	with open(fname, "wb") as f:
		# VERSION must be first because loading depends on it.
		f.write('VERSION\t{}\n'.format(version))
		for n in name_map:
			f.write('MAP\t{}\t{}\n'.format(n, name_map[n]))
		for t in timers:
			start = date_to_str(t.start)
			stop = date_to_str(t.end)
			f.write('TIMER\t{}\t{}\t{}\t{}\n'.format(start, stop, t.name, t.comment))
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
				if re.search(name, t.name):
					name = t.name
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

def stop_timer():
	global save_changes, timers
	if len(timers) == 0:
		return
	# Stop current timer if it was running, and adjust existing timers
	# in case "now" was adjusted by a command line options
	for i in xrange(len(timers)-1, -1, -1):
		t = timers[i]
		if now < t.start:
			print "Adjust", t.name
			print "  before", t.start, t.end
			t.start = now
			t.end = now
			print "   after", t.start, t.end
			save_changes = True
		elif t.active():
			t.end = now
			print "Stop", t.name, t.duration()
			save_changes = True
		elif now < t.end:
			print "Adjust", t.name
			print "  before", t.start, t.end
			t.end = now
			print "   after", t.start, t.end
			save_changes = True
		else:
			break

def start_timer(name, comment):
	global save_changes, timers
	timers.append(Timer(name, comment, now))
	save_changes = True
	print "Start", name, now

def same_day(prev_date, date):
	return (prev_date.year == date.year and prev_date.month == date.month
			and prev_date.day == date.day)

def same_week(prev_date, date):
	# The weeknumber in isocalendar() start with Monday
	return (prev_date.year == date.year and prev_date.month == date.month
			and prev_date.isocalendar()[1] == date.isocalendar()[1])

def same_month(prev_date, date):
	return prev_date.year == date.year and prev_date.month == date.month
		
def add_duration(timer, total):
	n = timer.name
	d = timer.duration()
	if n in total[0]:
		total[0][n] += d
	else:
		total[0][n] = d
	for t in timer.tags:
		if t in total[1]:
			total[1][t] += d
		else:
			total[1][t] = d

def duration_str(d):
	minutes, seconds = divmod(d.total_seconds(), 60)
	hours, minutes = divmod(minutes, 60)
	if hours != 0 or minutes != 0:
		return '{:>3d}:{:>02d}'.format(int(hours), int(minutes))
	if seconds != 0:
		return '   .{:>02d}'.format(int(seconds))
	return '      '

def print_durations(total):
	t = datetime.timedelta(0)
	for d in total[0]:
		print " ", duration_str(total[0][d]), d
		t = t + total[0][d]
	print " ", duration_str(t), "TOTAL"
	for d in total[1]:
		print " ", duration_str(total[1][d]), d

def print_daily(date, total):
	print 'day   {:%Y-%m-%d}'.format(date)
	print_durations(total)

def print_weekly(date, total):
	# weekday() returns Monday as 0
	first = datetime.date.fromordinal(date.toordinal()-date.weekday())
	print 'week  {:%Y-%m-%d}'.format(first)
	print_durations(total)

def print_monthly(date, total):
	print 'month {:%Y-%m}'.format(date)
	print_durations(total)

def report():
	if len(timers) == 0:
		print "No timers to report"
		return
	prev_date = timers[0].start
	daily_total = ({}, {})
	weekly_total = ({}, {})
	monthly_total = ({}, {})
	for t in timers:
		date = t.start
		if not same_day(prev_date, date):
			print_daily(prev_date, daily_total)
			daily_total = ({}, {})
		if not same_week(prev_date, date):
			print_weekly(prev_date, weekly_total)
			weekly_total = ({}, {})
		if not same_month(prev_date, date):
			print_monthly(prev_date, monthly_total)
			monthly_total = ({}, {})
		add_duration(t, monthly_total)
		add_duration(t, weekly_total)
		add_duration(t, daily_total)
		prev_date = date
	print_daily(prev_date, daily_total)
	print_weekly(prev_date, weekly_total)
	print_monthly(prev_date, monthly_total)

def add_duration_week(timer, total):
	day = timer.start.weekday()
	n = timer.name
	d = timer.duration()
	if n not in total[0]:
		total[0][n] = [ datetime.timedelta(0) ] * 8
	total[0][n][day] += d
	total[0][n][7] += d
	for t in timer.tags:
		if t not in total[1]:
			total[1][t] = [ datetime.timedelta(0) ] * 8
		total[1][t][day] += d
		total[1][t][7] += d

def print_durations_week(total):
	# TODO: format the name at the end of a line to fit the terminal width.
	t = [ datetime.timedelta(0) ] * 8
	print "    Mon    Tue    Wed    Thu    Fri    Sat    Sun  Total  Name"
	for n in sorted(total[0].keys()):
		line = ""
		for day in xrange(0, 8):
			line += " " + duration_str(total[0][n][day])
			t[day] = t[day] + total[0][n][day]
		line += "  " + n
		print line
	line = ""
	for day in xrange(0, 8):
		line += " " + duration_str(t[day])
	line += "  TOTAL"
	print line
	print " ", "-" * 76
	for n in sorted(total[1].keys()):
		line = ""
		for day in xrange(0, 8):
			line += " " + duration_str(total[1][n][day])
			t[day] = t[day] + total[1][n][day]
		line += "  " + n
		print line
	line = ""
	for day in xrange(0, 8):
		line += " " + duration_str(t[day])
	line += "  TOTAL"
	print line
	print " ", "-" * 76

def print_weekly_cal(date, total):
	# weekday() returns Monday as 0
	first = datetime.date.fromordinal(date.toordinal()-date.weekday())
	# print 'week  {:%Y-%m-%d}'.format(first)
	line = ""
	for day in xrange(0, 7):
		line += '  {:%m-%d}'.format(first + datetime.timedelta(days=day))
	print line
	print_durations_week(total)

def report_cal():
	if len(timers) == 0:
		print "No timers to report"
		return
	prev_date = timers[0].start
	weekly_total = ({}, {})
	monthly_total = ({}, {})
	for t in timers:
		date = t.start
		if not same_week(prev_date, date):
			print_weekly_cal(prev_date, weekly_total)
			weekly_total = ({}, {})
		if not same_month(prev_date, date):
			print_monthly(prev_date, monthly_total)
			monthly_total = ({}, {})
		add_duration(t, monthly_total)
		add_duration_week(t, weekly_total)
		prev_date = date
	print_weekly_cal(prev_date, weekly_total)
	print_monthly(prev_date, monthly_total)
	
main()

# vim: tabstop=4:shiftwidth=4:noexpandtab

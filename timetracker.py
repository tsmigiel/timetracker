#!/usr/bin/env python
#
#  TimeTracker
#
help_text = """
Setup:
  Copy timetracker.py somewhere.
  Create a shorthand called tt.  For example:
  - ln -snf /path/to/timetracker.py ~/bin/tt
  - alias tt="/path/to/timetracker.py"

Typical usage:
  tt  name...       # start a timer
  tt  -l|--leap M name...  # start a timer M minutes ago
  tt  -a|--at HH:MM name...  # start a timer at HH:MM (24-hour clock)
  tt  -s|--stop     # stop active timer
  tt                # prints active timer
  tt  -r|--report   # prints a report
  tt  -c|--calendar # a report like a calendar

  name... - {[@]word}+ 
  The list of words indicate the name.  It will do a RE search for the most
  recent matching name, otherwise use the words as is.  Timers with the same
  name are combined in reports.  One or more words can be prefixed with @ to
  indicate a tag.  Reports will show the total time of each tag.

Gui usage
  The current timer is the first row and is prefixed with + when active.
  Durations are rounded up to the next minute.

  Stop - stop any active timer
  Start/Run - start the currently selected row by running tt with the text box
              as arguments (not searching names) or edit the text box to run
			  aribtrary arguments
  Reload - reload the timer in case they were modified somewhere else
  Stdout - open a window displaying stdout (useful to see reports)
  Help - open a window with this message

  Double clicking on a row will start a new timer with exactly that name.
  Press enter in text box will run tt with the text as is, i.e., potentially
  searching for a timer name.

Examples:
  tt @tc-123 bug 456 bad cse
  tt @tc-222 bug 333 optnone
  tt @tc-123 # uses the previous matching name 
  tt -l 20 @tc-222  # oops, should have started the timer 20 minutes ago
  tt @lunch
  tt -a 14:00 @tc-222  # oops, forgot to start the timer after lunch
  tt -s
  tt -r
  tt -c

Keep track of timers.  Only one timer is ever running at a time.
When run with no arguments print the duration of the active timer.
When run with position arguments, create a new timer with the arguments as
the name.  If there is more than 1 positional argument, they are combined
with spaces to make 1 name.  Any word prefixed with @ is a tag which can be
used while printing reports.  Each timer can also have a comment which is
started with a :.  Comments are not used during name matching.
There is no real connection of one timer to the other, except that reports
will combine timers with the same name in some way.
As a convenience, a name specified on the command line will be resolved
through the following steps:
 1) do a regular expression search starting with the most recent timer and
    use the first match as the name
 2) use the name as is

IMPLEMENTATION

There is only one data structures.
1. array of timers
  - record start time, end time, and name
   - tuple of (string, datetime, datetime)
2. TODO: an array to archive older timers so they aren't include in reports
  or searches

Basic operation:
1. read file of timers
2. parse and handle arguments
  - print the active timer when no options or arguments
  - start new timer when just name arguments
  - handle special options
3. save file
"""

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
				  help="use this name explicitly, don't search")
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
parser.add_option("-a", "--at",
				  dest="at_time", metavar="N", type="str",
				  help="Start timer as if it was today at HH:MM (24-hour clock)")

parser.add_option("-b", "--report-break-in-service",
				  action="store_true", dest="report_break_in_service", default=False,
				  help="generate a break in service report")

parser.add_option("-g", "--gui",
				  action="store_true", dest="gui", default=False,
				  help="Run a simple Qt gui (ignores other arguments)")

(options, optargs) = parser.parse_args()

# TODO: Hmm, it's convenient to use globals, but should I not use them? I was
# trying to avoid creating a class, but that might be the best solution. 
# One nasty requirement of globals is having to declare them as global in
# functions, which leads to non-obvious errors when you don't.

version = 2
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
			dur = datetime.datetime.now().replace(microsecond=0) - self.start
		else:
			dur = self.end - self.start
		return dur

	def description(self):
		if self.end:
			return "{:%Y-%m-%d %H:%M}-{:%H:%M} | {}".format(self.start, self.end, self.name)
		return "{:%Y-%m-%d %H:%M}-now | {}".format(self.start, self.name)


def main():
	global now
	fname = os.path.expanduser(options.filename)
	if os.path.exists(fname):
		load(fname)
	name = None
	if options.gui:
		gui()
		return
	if optargs:
		name, sep, comment = " ".join(optargs).partition(":")
		name = resolve_name(name)
	if options.leap:
		now = now - datetime.timedelta(seconds = options.leap*60)
	if options.at_time:
		clock = datetime.datetime.strptime(options.at_time, "%H:%M")
		now = now.replace(hour = clock.hour, minute = clock.minute, second = 0, microsecond = 0)
	if options.stop:
		stop_timer()
	elif name:
		stop_timer()
		start_timer(name, comment)
	elif options.report:
		report()
	elif options.report_cal:
		report_cal()
	elif options.report_break_in_service:
		report_break_in_service()
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
	global timers, save_changes
	timers = []
	if options.verbose:
		print "loading", fname
	with open(fname, "rb") as f:
		load_version = 0
		for line in f:
			field = line.rstrip('\r\n').split('\t')
			if field[0] == 'TAGCHAR':
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
			print "loaded", len(timers), "timers"
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
		for t in timers:
			start = date_to_str(t.start)
			stop = date_to_str(t.end)
			f.write('TIMER\t{}\t{}\t{}\t{}\n'.format(start, stop, t.name, t.comment))
		if options.verbose:
			print "saved", len(timers), "timers"

def resolve_name(name):
	if not options.explicit:
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

def stop_timer():
	global save_changes, timers
	if len(timers) == 0:
		return
	# Stop current timer if it was running, and adjust existing timers
	# in case "now" was adjusted by a command line options
	for i in xrange(len(timers)-1, -1, -1):
		t = timers[i]
		if now < t.start:
			print "Adjust:", t.name
			print "  before", t.start, t.end
			t.start = now
			t.end = now
			print "   after", t.start, t.end
			save_changes = True
		elif t.active():
			t.end = now
			print "Stop:", t.name, t.duration()
			save_changes = True
		elif now < t.end:
			print "Adjust:", t.name
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
	print "Start:", name, now

def same_day(prev_date, date):
	return prev_date.toordinal() == date.toordinal()

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
	for n in sorted(total[0].keys()):
		print " ", duration_str(total[0][n]), n
		t = t + total[0][n]
	print " ", duration_str(t), "TOTAL"
	for n in sorted(total[1].keys()):
		print " ", duration_str(total[1][n]), n

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
	for n in sorted(total[0].keys()):
		line = ""
		for day in xrange(0, 8):
			line += duration_str(total[0][n][day]) + " "
			t[day] = t[day] + total[0][n][day]
		line += " " + n
		print line
	line = ""
	for day in xrange(0, 8):
		line += duration_str(t[day]) + " "
	line += " TOTAL"
	print line
	print "-" * 78
	for n in sorted(total[1].keys()):
		line = ""
		for day in xrange(0, 8):
			line += duration_str(total[1][n][day]) + " "
		line += " " + n
		print line
	print "=" * 78

def print_weekly_cal(date, total):
	# weekday() returns Monday as 0
	first = datetime.date.fromordinal(date.toordinal()-date.weekday())
	# print 'week  {:%Y-%m-%d}'.format(first)
	line = ""
	line2 = ""
	for day in xrange(0, 7):
		d = first + datetime.timedelta(days=day)
		if same_month(date, d):
			line += ' {:%m-%d} '.format(d)
			line2 += '   {:%a} '.format(d)
		else:
			line += '       '
			line2 += '       '
	print line
	print line2, "Total  Name"
	print_durations_week(total)

def report_cal():
	if len(timers) == 0:
		print "No timers to report"
		return
	print "=" * 78
	prev_date = timers[0].start
	weekly_total = ({}, {})
	monthly_total = ({}, {})
	for t in timers:
		date = t.start
		if not same_month(prev_date, date):
			print_weekly_cal(prev_date, weekly_total)
			print_monthly(prev_date, monthly_total)
			print "=" * 78
			weekly_total = ({}, {})
			monthly_total = ({}, {})
		elif not same_week(prev_date, date):
			print_weekly_cal(prev_date, weekly_total)
			weekly_total = ({}, {})
		add_duration(t, monthly_total)
		add_duration_week(t, weekly_total)
		prev_date = date
	print_weekly_cal(prev_date, weekly_total)
	print_monthly(prev_date, monthly_total)

def report_break_in_service():
	prev_date = timers[0].start
	for t in timers:
		date = t.start
		start_break = prev_date.toordinal() + 1
		end_break = date.toordinal() - 1
		if end_break - start_break + 1 > 3:
			print '{:%b %d} - {:%b %d}  {:2d} days'.format(datetime.date.fromordinal(start_break), datetime.date.fromordinal(end_break), end_break - start_break + 1)
		prev_date = date

# Looks messy but I kept it in the same file for easy installation
def gui():
	from PySide import QtCore
	from PySide import QtGui
	global timers, reportwin

	class TextWindow(QtGui.QWidget):
		def __init__(self, title, text, parent=None):
			super(TextWindow, self).__init__(parent)
			self.setWindowTitle(title)
			self.resize(750, 300)
			self.textedit = QtGui.QTextEdit(self)
			self.textedit.setFont(QtGui.QFont("Courier New", 14))
			self.textedit.setReadOnly(True)
			self.textedit.setPlainText(text)
			vb = QtGui.QVBoxLayout()
			vb.addWidget(self.textedit)
			self.setLayout(vb)
		def write(self, txt):
			self.textedit.insertPlainText(str(txt))

	# Display the latest 100 timer names and duration, most recent first.
	class TimerTableModel(QtCore.QAbstractTableModel):
		def __init__(self, parent, header, *args):
			QtCore.QAbstractTableModel.__init__(self, parent, *args)
			self.header = header
		def rowCount(self, parent):
			return min(100,len(timers))
		def columnCount(self, parent):
			return 2
		def data(self, index, role):
			if not index.isValid():
				return None
			if role == QtCore.Qt.ToolTipRole:
				t = timers[-1-index.row()]
				if t:
					return t.description()
			if role != QtCore.Qt.DisplayRole:
				return None
			t = timers[-1-index.row()]
			if index.column() == 0:
				return t.name
			elif index.column() == 1:
				d = int((t.duration().total_seconds() + 60) / 60) # round up 
				if t.active():
					prefix = "+"
				else:
					prefix = " "
				return prefix + "{:d}:{:02d}".format(int(d / 60), d % 60)
			return None
		def headerData(self, col, orientation, role):
			if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
				return self.header[col]
			return None
		def getTimer(self,row):
			return timers[-1-row]

	app = QtGui.QApplication(sys.argv)
	app.setApplicationName("TimeTracker")

	# Redirect stdout to a window (that implements write())
	reportwin = TextWindow("Stdout", "")
	sys.stdout = reportwin

	win = QtGui.QMainWindow()
	win.setWindowTitle('Time Tracker')
	win.resize(300, 450)

	statusbar = QtGui.QStatusBar()
	win.setStatusBar(statusbar)
	statusbar.showMessage("ready")

	central = QtGui.QWidget(win)
	win.setCentralWidget(central)
	layout = QtGui.QVBoxLayout()
	central.setLayout(layout)
	entry = QtGui.QLineEdit(central)
	layout.addWidget(entry)
	table_model = TimerTableModel(central, ['timer', 'duration'])
	table_view = QtGui.QTableView()
	table_view.setModel(table_model)
	table_view.setFont(QtGui.QFont("Courier New", 14))
	table_view.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
	table_view.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
	table_view.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.Stretch)
	table_view.resizeColumnsToContents()
	layout.addWidget(table_view)

	# A timer to update duration of an active task.
	# TODO: only run the timer when there is an active task
	def updateTimer():
		if timers[-1].active():
			index = table_model.createIndex(0, 1, None)
			table_model.dataChanged.emit(index, index)
	timer = QtCore.QTimer()
	timer.setInterval(30000) # 30 seconds
	timer.timeout.connect(updateTimer)
	timer.start()

	# Re-call main() with new command line (No -g)
	def run_command(cmd):
		global options, optargs, parser, now, save_changes
		statusbar.showMessage(sys.argv[0] + " " + " ".join(cmd))
		save_changes = False
		now = datetime.datetime.now().replace(microsecond=0)
		(options, optargs) = parser.parse_args(cmd)
		options.gui = False;
		main()
		table_model.reset()
		sb = table_view.verticalScrollBar()
		if sb:
			sb.setSliderPosition(0)

	# A toolbar is an easy way to make a bunch of buttons
	toolbar = QtGui.QToolBar()
	def do_stop():
		run_command(["-s"])
		return
	action = QtGui.QAction("Stop", win)
	action.triggered.connect(do_stop)
	toolbar.addAction(action)
	def do_run():
		run_command(["-e"] + entry.displayText().split())
	action = QtGui.QAction("Start/Run", win)
	action.triggered.connect(do_run)
	toolbar.addAction(action)
	def do_load():
		global options
		fname = os.path.expanduser(options.filename)
		if os.path.exists(fname):
			load(fname)
			table_model.reset()
			statusbar.showMessage("Reloaded " + fname)
		else:
			statusbar.showMessage("Could not reload " + fname)
	action = QtGui.QAction("Reload", win)
	action.triggered.connect(do_load)
	toolbar.addAction(action)
	def do_report():
		global reportwin
		reportwin.show()
	action = QtGui.QAction("Stdout", win)
	action.triggered.connect(do_report)
	toolbar.addAction(action)
	def do_help():
		global helpwin
		helpwin = TextWindow("Help", help_text)
		helpwin.show()
	action = QtGui.QAction("Help", win)
	action.triggered.connect(do_help)
	toolbar.addAction(action)
	win.addToolBar(toolbar)

	# Connect table view and line box actions.
	def on_item_changed(selected, deselected):
		if selected[0]:
			t = table_model.getTimer(selected[0].top())
			if t:
				entry.setText(t.name)
				statusbar.showMessage(t.description())
		else:
			entry.setText("")
	def on_item_double(selected):
		t = table_model.getTimer(selected.row())
		if t:
			entry.setText(t.name)
			do_run()
	def on_return_pressed():
		run_command(entry.displayText().split())
	table_view.selectionModel().selectionChanged.connect(on_item_changed)
	table_view.doubleClicked.connect(on_item_double)
	entry.returnPressed.connect(on_return_pressed)

	win.show()
	win.activateWindow()
	win.raise_()
	app.exec_()

main()

# vim: tabstop=4:shiftwidth=4:noexpandtab

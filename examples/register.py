from davislib import Term, ScheduleBuilder
from datetime import datetime, timedelta
import sys
from getpass import getpass
from os.path import expanduser

def print_help():
	print('Example usage: python3 register.py 2015 fall "Schedule 1" --delay 2')
	print()
	print('DESCRIPTION: Waits for pass time (unless --now is provided) and then registers all courses in provided schedule.')
	print()
	print('Username and password will be prompted for at runtime, or optionally pulled from ~/.register_creds if it exists')
	print('~/.register_creds format:')
	print('kerberos_username')
	print('kerberos_password')
	print()
	print('ARGUMENTS:')
	print('year: four digit year of term')
	print()
	print('session: term session as described below in quotation marks', end='\n    ')
	print('fall quarter: "fall"', end='\n    ')
	print('fall semester: "fall semester"', end='\n    ')
	print('winter quarter: "winter"', end='\n    ')
	print('spring quarter: "spring"', end='\n    ')
	print('spring semester: "spring semester"', end='\n    ')
	print('first summer session: "summer 1"', end='\n    ')
	print('special summer session: "summer special"', end='\n    ')
	print('second summer session: "summer 2"')
	print()
	print('schedule: name of schedule')
	print()
	print('--delay n: Optional number of seconds to delay registration after pass time. Default is 3 to account for discrepencies in time syncronization. ')
	print()
	print('--now: If provided, immediately attempts to register courses instead of waiting until pass time + delay. ')

def main():
	if len(sys.argv) < 4:
		print('USAGE: python3 register.py [--help] year session schedule [--delay 3 | --now]')
		if len(sys.argv) > 1 and sys.argv[1] == '--help':
			print_help()
		return

	try:
		creds_path = expanduser('~/.register_creds')
		secret = open(creds_path, 'r').readlines()
		username = secret[0].strip()
		password = secret[1].strip()
	except IndexError:
		raise Exception('Malformed .register_creds file')
	except IOError:
		username = input('Kerberos username: ')
		password = getpass('Kerberos password: ') 

	year = sys.argv[1]
	session = sys.argv[2]
	schedule = sys.argv[3]
	sb = ScheduleBuilder(username, password)
	term = Term(year, session)
	now = datetime.now()

	if sys.argv[-1] == '--now':
		reg_time = now
	else: # Calculate time until registration
		delay = 0
		if sys.argv[-2] == '--delay':
			delay = int(sys.argv[-1])

		# Fetch pass times as datetime objects, then add delay
		pass_times = [t + timedelta(seconds=delay) for t in sb.pass_times(term)]

		if now > pass_times[0]: # has pass 1 already occured?
			if (now - pass_times[0]) < (pass_times[1] - now): # are we closer to pass 1 than to pass 2?
				reg_time = now 
			else: # closer to pass 2 than to pass 1
				if now > pass_times[1]: # are we beyond pass 2?
					reg_time = now 
				else: # pass 2 is upcoming
					reg_time = pass_times[1]
		else: # pass 1 has not occurred. wait for pass 1
			reg_time = pass_times[0]

	print('Registering in {0:.2f} seconds...'.format((reg_time - now).total_seconds()))
	sb.register_schedule(term, schedule, at=reg_time)
	print('Registered')

if __name__ == '__main__':
	main()
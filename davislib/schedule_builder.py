"""
davislib.schedule_builder

This module provides an interface to Schedule Builder
"""
from .models import ProtectedApplication, Course, Term
from bs4 import BeautifulSoup
import re
import itertools
import time
from datetime import datetime

class RegistrationError(Exception):
    pass

class ScheduleBuilder(ProtectedApplication):
    """
    Interface to Schedule Builder
    """
    BASE='https://students.my.ucdavis.edu/schedulebuilder'
    REGISTER_ENDPOINT='/addCourseRegistration.cfm'
    ADD_COURSE_ENDPOINT='/addCourseToSchedule.cfm'
    REMOVE_COURSE_ENDPOINT='/removeCourseFromSchedule.cfm'
    HOME_ENDPOINT='/index.cfm'
    REGISTRATION_ERRORS=['You are already enrolled or waitlisted for this course',
                         'Registration is not yet available for this term',
                         'Could not register you for this course']
    def registered_courses(self, term):
        """
        Returns list of CRNs of registered courses for term
        Parameters:
            term: Term object
        """
        params = {'termCode': term.code}
        r = self.get(self.HOME_ENDPOINT, params=params)
        matches = re.finditer(r'CourseDetails.t(.+?).REGISTRATION_STATUS = "(Registered|Waitlisted)"', r.text)
        crns = list()
        
        for match in matches:
            crns.append(match.group(1))

        return crns
    
    def pass_times(self, term):
        """
        Returns tuple (datetime object for pass 1, datetime object for pass 2)
        If passtimes are not available, returns None
        Parameters:
            term: Term object
        """
        params = {'termCode': term.code}
        r = self.get(self.HOME_ENDPOINT, params=params)

        match = re.search(r'PassTime1":new Date\((.+?)\),"PassTime2":new Date\((.+?)\)}', r.text)
        try:
            js_args = list(zip(*[g.split(',') for g in match.groups()]))
            args = [js_args[0], # years
                    [s.split(' ')[0] for s in js_args[1]], # months
                    js_args[2], # days
                    js_args[3], # hours
                    js_args[4]] # minutes

            args = [(int(a), int(b)) for a,b in args]
            return (datetime(*[a[0] for a in args]),
                    datetime(*[a[1] for a in args]))
        except AttributeError:
            return None

    def schedules(self, term, include_units=False):
        """
        Returns dictionary of schedules with schedule names as keys and lists of CRNs as values
        Parameters:
            term: Term object
            include_units: Optional boolean parameter. 
                            If True, returned dictionary includies lists of tuple (CRN, units) as values.
                            Useful if returned courses are used in registration, as both CRN and course 
                            units are required. 
        """
        params = {'termCode': term.code}
        r = self.get(self.HOME_ENDPOINT, params=params)
        soup = BeautifulSoup(r.text, 'html.parser')
        schedules = dict()
        # Finding schedule names
        name_matches = list(re.finditer('Schedules\[Schedules\.length\] = \{"Name":"(.+?)"',
                                   r.text))
        course_re = re.compile('Schedules\[Schedules\.length \- 1\]\.SelectedList\.t'
                               '([0-9A-Z]+) =.+?"UNITS":"([0-9])"', flags=re.DOTALL)
        start = 0

        for idx, name_match in enumerate(name_matches):
            name = name_match.group(1)
            schedules[name] = list()

            try:
                end = name_matches[idx + 1].start()
            except IndexError:
                end = len(r.text)
            course_match = None
            for course_match in course_re.finditer(r.text, name_match.start(), end):
                crn = course_match.group(1)
                if include_units:
                    units = int(course_match.group(2))
                    schedules[name].append((crn, units))    
                else:
                    schedules[name].append(crn)

        return schedules

    def add_course(self, term, schedule, crn):
        """
        Adds course to schedule
        Parameters:
            term: Term object
            schedule: Name of schedule
            crn: course registration number of course to be added
        """ 
        query = {'Term': term.code,
                 'Schedule': schedule,
                 'CourseID': crn,
                 'ShowDebug': 0,
                 '_': int(float(time.time()) * 10**3)}

        self.get(self.ADD_COURSE_ENDPOINT, params=query)

    def remove_course(self, term, schedule, crn):
        """
        Removes course from schedule
        Parameters:
            term: Term object
            schedule: Name of schedule
            crn: course registration number of course to be removed
        """
        query = {'Term': term.code,
                 'Schedule': schedule,
                 'CourseID': crn,
                 'ShowDebug': 0,
                 '_': int(float(time.time()) * 10**3)}

        self.get(self.REMOVE_COURSE_ENDPOINT, params=query)
    
    def register_schedule(self, term, schedule, allow_waitlisting=True, at=None):
        """
        Registers all classes in provided schedule
        Parameters:
            term: Term object
            schedule: name of schedule. case sensitive
            allow_waitlisting: True/False, indicating if courses should be registered even if student will
                                            be placed on waitlist
            at: optional datetime object indicating future time at which registration will be executed
                    useful if you want to register at pass time
        """
        items = self.schedules(term, include_units=True)[schedule]
        self.register_courses(term, schedule, items, allow_waitlisting, at)

    def register_courses(self, term, schedule, items, allow_waitlisting=True, at=None):
        """
        Registers all classes provided in 'items'
        Parameters:
            term: Term object
            schedule: name of schedule containing courses. 
            items: list of tuple (crn, units) 
                    (note: tuples are provided in returned dictionary from ScheduleBuilder.schedules)
            allow_waitlisting: True/False, indicating if courses should be registered even if student will
                                            be placed on waitlist
            at: optional datetime object indicating future time at which registration will be executed
                    useful if you want to register at pass time
        """
        crns, units = zip(*items)
        query = {'Term': term.code,
                 'CourseCRNs': ','.join([str(x) for x in crns]),
                 'Schedule': schedule,
                 'WaitlistedFlags': 'Y' if allow_waitlisting else 'N',
                 'Units': ','.join([str(x) for x in units]),
                 'ShowDebug': 0,
                 '_': int(float(time.time()) * 10**3) # timestamp in milliseconds
                 }

        if at:
            seconds = (at - datetime.now()).total_seconds()
            if seconds > 0:
                time.sleep(seconds) 

        r = self.get(self.REGISTER_ENDPOINT, params=query)
        # Error checking
        for e in self.REGISTRATION_ERRORS:
            if e in r.text:
                raise RegistrationError(e)

"""
davislib.schedule_builder

This module provides an interface to Schedule Builder
"""
from .models import ProtectedApplication, Course, Term
from bs4 import BeautifulSoup
import re
import itertools
import logging
import json
import requests
import time
from datetime import datetime, timedelta

class RegistrationError(Exception):
    pass

def term_sensitive(func):
    def visit_sb_index(self, term, *args, **kwargs):
        if self.last_term_visited != term:
            self.get('{}?termCode={}'.format(self.HOME_ENDPOINT, term.code))
            self.last_term_visited = term

        return func(self, term, *args, **kwargs)
    return visit_sb_index

class ScheduleBuilder(ProtectedApplication):
    """
    Interface to Schedule Builder
    """
    BASE='https://students.my.ucdavis.edu/schedulebuilder'
    REGISTER_ENDPOINT='/addCourseRegistration.cfm'
    ADD_COURSE_ENDPOINT='/addCourseToSchedule.cfm'
    REMOVE_COURSE_ENDPOINT='/removeCourseFromSchedule.cfm'
    COURSE_SEARCH_ENDPOINT='/course_search/course_search_results.cfm'
    HOME_ENDPOINT='/index.cfm'
    REGISTRATION_ERRORS=['You are already enrolled or waitlisted for this course',
                         'Registration is not yet available for this term',
                         'Could not register you for this course']
    
    def __init__(self, *args, **kwargs):
        super(__class__, self).__init__(*args, **kwargs)

        self.last_term_visited = None


    def _normalize_course_query_response(self, json_obj):
        response_items = [dict(zip(json_obj['COLUMNS'], values)) for values in json_obj['DATA']]
        for idx, item_dict in enumerate(response_items):
            nrml_item = dict()
            for key, value in item_dict.items():
                if isinstance(value, str) and value.startswith('{"QUERY":'):
                    nrml_item[key] = self._normalize_course_query_response(json.loads(value)['QUERY'])
                else:
                    nrml_item[key] = value

            response_items[idx] = nrml_item

        return response_items

    def _course_from_query_response(self, term, response):
        """
        Returns Course object populated by parsing response
        """
        units_low, units_hi = float(response['UNITS_LOW']), float(response['UNITS_HIGH'])
        if units_low > units_hi: 
            # Yes, this is an actual response case...
            # Occurs when a course has a constant # of units.
            # I think units_hi should equal units_low when actual units is constant.
            units_hi = units_low 

        instructor_name = instructor_email = None
        try:
            instructor_meta = next(instr for instr in response['INSTRUCTORS'] if instr['PRIMARY_IND'] == 'Y')
            instructor_name = '{} {}'.format(instructor_meta['FIRST_NAME'], instructor_meta['LAST_NAME'])
            instructor_email = instructor_meta['EMAIL']
        except StopIteration:
            # No instructor specified
            pass

        ge_areas = None
        try:
            area_codes = filter(None, response['GE3CREDIT'].split(','))
            ge_areas = [GE_AREA_NAMES_BY_SB_CODE[area_code] for area_code in area_codes]
        except KeyError as e:
            logging.exception('Unrecognized GE code')

        meetings = list()
        for meeting in response['COURSEMEETINGDATA']:
            days = meeting['WEEKDAYS'].replace(',', '')
            times = None
            try:
                begin_hour, begin_minutes = meeting['BEGIN_TIME'][:2], meeting['BEGIN_TIME'][2:]
                end_hour, end_minutes = meeting['END_TIME'][:2], meeting['END_TIME'][2:]
                begin = timedelta(hours=int(begin_hour), minutes=int(begin_minutes))
                end = timedelta(hours=int(end_hour), minutes=int(end_minutes))
                times = (begin, end)
            except TypeError:
                # times are None, indicating TBA
                pass

            meeting = {
                'days': days,
                'times': times,
                'location': '{} {}'.format(meeting['BLDG_DESC'], meeting['ROOM']),
                'type': meeting['MEET_TYPE_DESC_SHORT']
            }
            meetings.append(meeting)

        final_exam = None
        try:
            final_exam = datetime.strptime(response['FINALEXAMSTARTDATE'], '%B, %d %Y %H:%M:%S')
        except TypeError:
            # No final exam
            pass

        return Course(
            term=term,
            crn=response['PASSEDCRN'],
            subject_code=response['SUBJECT_CODE'],
            name='{} {}'.format(response['SUBJECT_CODE'], response['COURSE_NUMBER']),
            number=response['COURSE_NUMBER'],
            section=response['SEC'],
            title=response['TITLE'],
            description=response['DESCRIPTION'],
            instructor_consent_required=bool(int(response['CONSENTOFINSRUCTORREQUIRED'])),
            units=(units_low, units_hi),
            instructor=instructor_name,
            instructor_email=instructor_email,
            ge_areas=ge_areas,
            available_seats=response['BLEND_SEATS_AVAIL'],
            wl_length=response['BLEND_WAIT_COUNT'],
            meetings=meetings,
            final_exam=final_exam,
            drop_time=response['ALLOWEDDROPDESC'],
            prerequisites=response['PREREQUISITES'])
    
    @term_sensitive
    def course_query(self, term, **kwargs):
        """
        Returns list of course objects for a provided query 
        Parameters:
            term: Term object

            (kwarg) course_number: course number
            (kwarg) subject: code, length 3
            (kwarg) instructor: first OR last name (ScheduleBuilder does not support full name search. What a shame...)
            (kwarg) start: earliest desired start time, hour, 0-23
            (kwarg) end: latest desired end time, hour, 0-23
            (kwarg) level: unit range string, i.e., '001-099', ..., '300-399'
            (kwarg) units: 1-12
            }
        """
        data = {
            'course_number': kwargs.get('course_number', ''),
            'subject': kwargs.get('subject', ''),
            'instructor': kwargs.get('instructor', ''),
            'course_start_eval': 'After', # todo verify vs 'at'
            'course_start_time': kwargs.get('start', '-'), # todo parse arg into correct time
            'course_end_eval': 'Before', # todo verify vs 'at'
            'course_end_time': kwargs.get('end', '-'), # todo parse arg into correct time,
            'course_level': kwargs.get('level', '-'),
            'course_units': kwargs.get('units', '-'),
            'course_status': 'ALL',
            'sortBy': '',
            'showMe': '',
            'runMe': '1',
            'clearMe': '1',
            'termCode': term.code,
            'expandFilters': ''
        }
        try:
            r = self.post(self.COURSE_SEARCH_ENDPOINT, data=data)
            results = json.loads(r.text)['Results'] # {'COLUMNS': [...], 'DATA': [[col1_data, ...], ...}
        except KeyError:
            r = self.post(self.COURSE_SEARCH_ENDPOINT, data=data)
            results = json.loads(r.text)['Results']

        nrml_course_responses = self._normalize_course_query_response(results)

        courses = [self._course_from_query_response(term, resp) for resp in nrml_course_responses]
        return courses

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

    @term_sensitive
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

    @term_sensitive
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

    @term_sensitive
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

GE_AREA_NAMES_BY_SB_CODE = {
    'AH': 'Arts & Humanities',
    'SE': 'Science & Engineering',
    'SS': 'Social Sciences', 
    'ACGH': 'American Cultures, Governance & History',
    'DD': 'Domestic Diversity',
    'OL': 'Oral Literacy',
    'QL': 'Quantitative Literacy', 
    'SL': 'Scientific Literacy', 
    'VL': 'Visual Literacy',
    'WC': 'World Cultures',
    'WE': 'Writing Experience'
}

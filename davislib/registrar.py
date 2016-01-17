"""
davislib.registrar

This module provides an interface to the University Registrar
"""
from .models import Application, Course, Term
from bs4 import BeautifulSoup
from bs4.element import NavigableString
import datetime
import re
from enum import Enum
import logging

class InvalidCrnOrTermError(Exception):
    pass

class QueryError(Exception):
    pass

class Registrar(Application):

    """
    Wrapper for university registrar
    http://registrar.ucdavis.edu/
    """
    BASE='https://registrar.ucdavis.edu'
    COURSE_DETAIL_ENDPOINT='/courses/search/course.cfm'
    COURSE_SEARCH_ENDPOINT='/courses/search/course_search_results_mod8.cfm'

    def course_detail(self, term, crn):
        """
        Searches for course with given crn and returns Course object
        Parameters:
            crn: course reference number
            term: Term object
        """
        params = {'crn': crn,
                  'termCode': term.code}

        r = self.get(self.COURSE_DETAIL_ENDPOINT, params=params)

        course_attrs = self._parse_course(r.text, term)
        course_attrs['term'] = term
        course_attrs['crn'] = crn

        return Course(**course_attrs)

    def course_query(self, term, **kwargs):
        """
        Queries university registrar and returns list of course CRNs
        Parameters:
            term: Term object
            kwargs:
                crn: five digit course reference number
                name: partial or complete course name,
                             e.g. 'ASA' or 'ASA 001'
                title: course title, e.g. Intro to Programming
                instructor: first or last name
                subject: course subject in short form
                         e.g. 'ECS'
                start: earliest desired start time, as hour in 24-hr format
                end: latest desired end time, as hour in 24hr format
                days: list [QueryOptions.Day, ...]
                only_open: boolean
                level: QueryOptions.Level
                units: int in [1,9]
                only_virtual: boolean
                ge_areas: list [QueryOptions.GEArea, ...]
        """
        if type(term) is not Term:
            raise ValueError("provided term is not an instance of Term class")

        query = self._map_params(term, **kwargs)
        r = self.post(self.COURSE_SEARCH_ENDPOINT,
                      data=query)
        soup = BeautifulSoup(r.text, 'html.parser')

        courses = list()
        for row in soup.find_all('tr'):
            cell = row.find('td')
            if len(cell.contents) and 'Please refine' in cell.contents[0]:
                raise QueryError('Registrar response: "{}"'.format(cell.string))
            if 'onclick' in cell.attrs.keys():
                match = re.search(r'crn=(.+?)&', cell['onclick'])
                courses.append(match.group(1))

        return list(set(courses)) # CRNs are unique

    def _map_params(self, term,
        crn=None,
        name=None,
        title=None,
        instructor=None,
        subject=None,
        start=None,
        end=None,
        days=None,
        only_open=None,
        level=None,
        units=None,
        only_virtual=None,
        ge_areas=None):
        """
        Maps the user-provided search query to a dictionary whose
        keys are identical to the registrar's form input names.
        Used to submit the search form.
        """#
        params = dict()
        params['termYear'], params['term'] = term.year, term.session.value
        params['termCode'] = term.code
        if crn: # CRN and Course Name are provided in same field. If CRN is provided, give it precedence.
            params['course_number'] = crn
        elif name:
            params['course_number'] = name
        params['course_title'] = title
        params['instructor'] = instructor
        params['subject'] = subject

        # Course Times
        if start:
            params['course_start_eval'] = 'After'
            if start < 12:
                # AM classes start on the hour
                params['course_start_time'] = '{}:00'.format(start)
            else:
                # PM classes start ten minutes after the hour
                params['course_start_time'] = '{}:10'.format(start)

        if end:
            params['course_end_eval'] = 'Before'
            if end < 12:
                # AM classes end ten minutes before the hour
                params['course_end_time'] = '{}:50'.format(end - 1)
            else:
                # PM classes end on the hour
                params['course_end_time'] = '{}:00'.format(end)

        # get enum value
        if days:
            params['days'] = [d.value for d in days]

        if only_open:
            params['course_status'] = 'Open'

        if level:
            params['course_level'] = level.value

        params['course_units'] = units

        if only_virtual:
            params['virtual'] = 'Y'

        if ge_areas:
            try:
                for area in ge_areas:
                    params[area.value[0]] = 'Y'
            except TypeError: # TypeError due to ge_credit not being iterable
                # Only one ge_credit value supplied
                params[ge_areas.value] = 'Y'

        return params

    def _parse_course_detail_cell(self, cell, term):
        """
        Returns tuple (key, value) representing cell contents

        Parameters:
            cell: BeautifulSoup tag representing table cell from course detail page

        """
        strong = cell.find('strong')
        if not strong:
            return None

        try:
            item = strong.string.strip()
        except AttributeError:
            item = strong.contents[0].strip()
        for i, c in enumerate(cell.contents):
            # Strip whitespace from all text elements
            strip_op = getattr(c, "strip", None)
            if callable(strip_op):
                cell.contents[i] = c.strip()

        if item == 'Subject Area:':
            subject = cell.contents[1]
            if subject.endswith(';'):
                subject = subject[:-1]
            return ('subject', subject)

        elif item == 'Instructor:':
            return ('instructor', cell.contents[4])

        elif item == 'Units:':
            units = None
            try:
                units = float(cell.contents[2])
            except ValueError:
                unit_range = cell.contents[2].split(' TO ') # Units are also provided as range
                if len(unit_range) == 1:
                    unit_range = cell.contents[2].split(' OR ') # OR was used in previous years

                if len(unit_range) == 2:
                    units = tuple([float(n) for n in unit_range])

                else: # Can't parse units; return raw string
                    units = cell.contents[2]
            return ('units', units)

        elif 'New GE Credit' in item:
            ge_areas = []
            for ge_content in cell.contents[1:]:
                if isinstance(ge_content, str) and len(ge_content):
                    ge_areas.append(ge_content)
            return ('ge_areas', ge_areas)

        elif item == 'Available Seats:':
            return ('available_seats', int(cell.contents[1]))

        elif item == 'Maximum Enrollment:':
            return ('max_enrollment', int(cell.contents[1]))

        elif item == 'Final Exam:':
            date = '{0} {1}'.format(term.year, ' '.join(cell.contents[1].split()))
            final_exam = None
            try:
                final_exam = datetime.datetime.strptime(date, '%Y %A, %B %d at %I:%M %p')
            except ValueError:
                final_exam = 'See Instructor'
            return ('final_exam', final_exam)

        elif item == 'Description:':
            return ('description', cell.contents[3].replace('\n', ' ').strip())

        elif item == 'Course Drop:':
            drop_text = cell.contents[1]
            match = re.match(r'^([0-9]+)', drop_text)
            drop_time = None
            if match:
                drop_time = int(match.group(1))
            else:
                drop_time = drop_text
            return ('drop_time', drop_time)
        elif item == 'Prerequisite:':
            prerequisite = cell.contents[3]
            if isinstance(prerequisite, str):
                return ('prerequisites', prerequisite)

    def _parse_meeting_times(self, times):
        times = times.string.split(' - ')
        try:
            start, end = times
            start_hour, start_minute = [int(t) for t in start.split(':')]
            end_hour, end_minute_and_ampm = end.split(':')
            end_hour = int(end_hour)
            end_minute, ampm = end_minute_and_ampm.split(' ')
            end_minute = int(end_minute)

            if ampm == 'PM':
                if start_hour < 9:
                    # this condition accounts for courses that start in the morning and end in afternoon
                    start_hour += 12
                if end_hour < 12:
                    end_hour += 12
            start = datetime.timedelta(hours=start_hour, minutes=start_minute)
            end = datetime.timedelta(hours=end_hour, minutes=end_minute)
            return (start, end)
        except ValueError:
            # Meeting times could not be parsed
            pass

    def _parse_course(self, course_html, term):
        if 'alert(' in course_html:
            # registrar uses alert message to indicate bad query
            raise InvalidCrnOrTermError()
            return None

        soup = BeautifulSoup(course_html, 'html.parser')
        attrs = dict()

        header = soup.find('h1')
        title_components = header.contents[1][3:].split()
        # Accounting for beautifulsoup output where ampersands in text are suffixed with ';'
        title_components = list(map(lambda title: re.sub(r'(.+&.+);$', r'\1', title), title_components))
        attrs['title'] = ' '.join([component.strip() for component in title_components if component.strip()])
        full_name = str(header.find('strong').string)

        name_components = full_name.split(' ')
        attrs['name'] = '{} {}'.format(*name_components[:2])
        attrs['number'] = name_components[1]
        attrs['section'] = None
        if len(name_components) == 3:
            attrs['section'] = name_components[2]

        # Set defaults for optional attributes

        attrs['ge_areas'] = list()
        attrs['available_seats'] = None
        attrs['max_enrollment'] = None
        # Simple key, value attributes
        for cell in soup.find_all('td'):
            contents = self._parse_course_detail_cell(cell, term)
            if contents:
                key, value = contents

                attrs[key] = value

        # Meeting times
        attrs['meetings'] = list()
        meetings_table = soup.find_all('table')[1]
        meeting_rows = meetings_table.find_all('tr')[1:] # all rows after the header
        for row in meeting_rows:
            cells = row.find_all('td')
            days, times, location = cells
            meeting = dict()
            meeting['days'] = days.string
            meeting['times'] = self._parse_meeting_times(times)
            meeting['location'] = location.string.strip()
            attrs['meetings'].append(meeting)

        return attrs

class QueryOptions(object):
    class GEArea(Enum):
        """
        Enum representation of all GE credit areas
        """
        AH = ('G3AH', 'Arts & Humanities')
        SE = ('G3SE', 'Science & Engineering')
        SS = ('G3SS', 'Social Sciences')
        ACGH = ('G3CGH', 'American Culture, Government, and History')
        DD = ('G3DD', 'Domestic Diversity')
        OL = ('G3O', 'Oral Literacy')
        QL = ('G3Q', 'Quantitative Literacy')
        SL = ('G3S', 'Scientific Literacy')
        VL = ('G3V', 'Visual Literacy')
        WC = ('G3WC', 'World Culture')
        WE = ('G3W', 'Writing Experience')

    class Day(Enum):
        MONDAY = 'M'
        TUESDAY = 'T'
        WEDNESDAY = 'W'
        THURSDAY = 'TR'
        FRIDAY = 'F'
        SATURDAY = 'S'

    class Level(Enum):
        LOWER_DIV = '001-099'
        UPPER_DIV_1 = '100-199'
        UPPER_DIV_2 = '200-299'
        UPPER_DIV_3 = '300-399'

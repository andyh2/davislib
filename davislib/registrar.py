"""
davislib.registrar

This module provides an interface to the University Registrar
"""
from .models import Application, Course, Term
from bs4 import BeautifulSoup
import datetime
import re
from enum import Enum

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
            crn: five digit course reference number
            course_name: partial or complete course name, 
                         e.g. 'ASA' or 'ASA 001'
            course_title: course title, e.g. Intro to Programming
            instructor: first or last name
            subject: str
            start: earliest desired start time, as hour in 24-hr format
            end: latest desired end time, as hour in 24hr format
            days: [QueryOptions.Days, ...]
            only_open: boolean
            level: QueryOptions.Levels
            units: int in [1,9]
            only_virtual: boolean
            ge_credit: [QueryOptions.GECredit, ...]
        """
        if type(term) is not Term:
            raise ValueError("provided term is not an instance of Term class")

        query = self._map_params(term, **kwargs)
        r = self.post(self.COURSE_SEARCH_ENDPOINT,
                      data=query)
        soup = BeautifulSoup(r.text)

        courses = list()
        for row in soup.find_all('tr'):
            for cell in row.find_all('td'):
                if len(cell.contents) and 'Please refine' in cell.contents[0]:
                    raise QueryError('Registrar response: "{}"'.format(cell.string))
                strong = cell.find('strong')
                if strong:
                    match = re.match('\d+', str(strong.string))
                    if match:
                        courses.append(match.group(0))

        return courses

    def _map_params(self, term,
        crn=None, 
        course_name=None, 
        course_title=None,
        instructor=None,
        subject=None,
        start=None,
        end=None,
        days=None,
        only_open=None,
        level=None,
        units=None,
        only_virtual=None,
        ge_credit=None):
        """
        Maps the user-provided search query to a dictionary whose 
        keys are identical to the registrar's form input names.
        Used to submit the search form. 
        """
        params = dict()
        params['termYear'], params['term'] = term.year, term.session.value
        params['termCode'] = term.code
        if crn: # CRN and Course Name are provided in same field. If CRN is provided, give it precedence.
            params['course_number'] = crn
        elif course_name:
            params['course_number'] = course_name
        params['course_title'] = course_title
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

        params['course_level'] = level
        params['course_units'] = units

        if only_virtual:
            params['virtual'] = 'Y'

        if ge_credit:
            for category in ge_credit:
                params[category.value[0]] = 'Y' 

        return params
        
    def _parse_course(self, course_html, term):
        if 'alert(' in course_html:
            # registrar uses alert message to indicate bad query
            raise InvalidCrnOrTermError()
            return None

        soup = BeautifulSoup(course_html)
        attrs = dict()

        header = soup.find('h1')
        attrs['name'] = header.find('strong').string
        attrs['title'] = header.contents[1][3:]
        
        name_components = attrs['name'].split(' ')
        attrs['number'] = name_components[1]
        attrs['section'] = None
        if len(name_components) == 3:
            attrs['section'] = name_components[2]

        attrs['ge_credit'] = list()

        # Simple key, value attributes
        for cell in soup.find_all('td'):
            strong = cell.find('strong')
            if strong:
                item = strong.string.strip()
                for i, c in enumerate(cell.contents):
                    # Strip whitespace from all text elements
                    strip_op = getattr(c, "strip", None)
                    if callable(strip_op):
                        cell.contents[i] = c.strip()

                if item == 'Subject Area:':
                    attrs['subject'] = cell.contents[1]

                elif item == 'Instructor:':
                    attrs['instructor'] = cell.contents[4]

                elif item == 'Units:':
                    try:
                        attrs['units'] = float(cell.contents[2])
                    except ValueError:
                        range_ = cell.contents[2].split(' TO ') # Units are also provided as range
                        if len(range_) == 2:
                            attrs['units'] = tuple([float(n) for n in range_])
                        else: # Can't parse units
                            attrs['units'] = cell.contents[2]

                elif 'New GE Credit' in item:
                    for ge_content in cell.contents[1:]:
                        if isinstance(ge_content, str) and len(ge_content):
                            attrs['ge_credit'].append(ge_content)

                elif item == 'Available Seats:':
                    attrs['available_seats'] = int(cell.contents[1])

                elif item == 'Maximum Enrollment:':
                    attrs['max_enrollment'] = int(cell.contents[1])

                elif item == 'Final Exam:':
                    date = '{0} {1}'.format(term.year, ' '.join(cell.contents[1].split())) 
                    try:
                        attrs['final_exam'] = datetime.datetime.strptime(date, '%Y %A, %B %d at %I:%M %p')
                    except ValueError:
                        attrs['final_exam'] = 'See Instructor'

                elif item == 'Description:':
                    attrs['description'] = cell.contents[3]

                elif item == 'Course Drop:':
                    attrs['drop_time'] = cell.contents[1]

        # Meeting times
        attrs['meetings'] = list()
        meetings_table = soup.find_all('table')[1]
        meeting_rows = meetings_table.find_all('tr')[1:] # all rows after the header
        for row in meeting_rows:
            cells = row.find_all('td')
            days, hours, location = cells
            meeting = dict()
            meeting['days'] = days.string
            meeting['hours'] = hours.string
            meeting['location'] = location.string
            attrs['meetings'].append(meeting)

        return attrs

class QueryOptions(object):
    class GECredit(Enum):
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
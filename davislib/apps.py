import requests
import re
import datetime
from bs4 import BeautifulSoup, element
from abc import abstractproperty
from enum import Enum

"""
Data containers
"""
class Term(object):
    """
    Container for term information
    """
    class Session(Enum):
        """
        Enum representation of all annual Term sessions
        """
        FALL_QUARTER = '10'
        FALL_SEMESTER = '09'
        SUMMER_SESSION_2 = '07'
        SUMMER_SPECIAL = '06'
        SUMMER_SESSION_1 = '05'
        SPRING_QUARTER = '03'
        SPRING_SEMESTER = '02'
        WINTER_QUARTER = '01'

        @classmethod
        def values(cls):
            """
            Returns list of values ('10', '09') 
            """
            return [m.value for m in cls.__members__.values()]

        def __str__(self):
            return self._name_.replace('_', ' ').title()

    def __init__(self, year, session):
        """
        Parameters:
            year: 
                e.g. 2014
            session: Session enumerated constant
                e.g. Term.Session.FALL_QUARTER
        """
        self.session = self.Session(session)
        self.year = year

    @property
    def name(self):
        return '{0} {1}'.format(self.session, self.year)

    def __str__(self):
        return '{0}{1}'.format(self.year, self.session.value)

    def __eq__(self, other):
        return str(self.year) == str(other.year) and self.session == other.session

"""
Base Classes
"""
class InvalidLoginError(Exception):
    pass

class MalformedPageError(Exception):
    pass

class UCDavisApplication(object):
    """
    Base class for UC Davis web app
    """
    USER_AGENT=('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537'
                '.36 (KHTML, like Gecko) Chrome/40.0.2214.115 Safari/537.36')

    def __init__(self, shared_app=None):
        """
        Parameters:
            (optional) shared_app: object deriving from UCDavisApplication 
                                   whose session will be used in new object
                                   (Specify this parameter if you wish to share cookies)
        """
        if shared_app:
            if isinstance(shared_app, __class__):
                self.s = shared_app.s
            else:
                raise ValueError("shared_app does not derive from UCDavisApplication")
        else:
            self.s = requests.Session()
            self.s.headers.update({'User-Agent': self.USER_AGENT})

    # @abstractproperty
    # def base(self):
    #     """
    #     Required property for subclasses representing
    #     first component of application "api" request. 
    #     This property is used in UCDavisApplication.request.
    #     """
    #     raise RuntimeError('{} does not define required property '
    #                        '"base"'.format(self.__class__))   

    def request(self, method, base, endpoint, **kwargs):
        return self.s.request(method, ''.join([base, endpoint]), **kwargs)

    def get(self, *args, **kwargs):
        """
        Executes GET request on application BASE at endpoint
        Parameters:
            see UCDavisApplication.request
        """
        return self.request('get', self.__class__.BASE, *args, **kwargs)
        # return self.s.get(''.join([base, endpoint]), **kwargs)

    def post(self, *args, **kwargs):
        """
        Executes POST request on application BASE at endpoint
        Parameters:
            see UCDavisApplication.request
        """
        return self.request('post', self.__class__.BASE, *args, **kwargs)
        # return self.s.post(''.join([base, endpoint]), **kwargs)

class UCDavisProtectedApplication(UCDavisApplication):
    """
    Base class for UC Davis web app relying on CAS (central authentication service)
    """         
    def __init__(self, username=None, password=None, shared_app=None):
        """
        Parameters:
            username: kerberos login id
            password: kerberos password
            (optional) shared_app: object deriving from UCDavisApplication
                                   whose session will be shared with self.
                                   if derives from UCDavisProtectedApplication,
                                   then username and password will be copied as well 
                                   for re-authentication.

        """
        super(__class__, self).__init__(shared_app=shared_app)

        # Initialize CAS class with self as shared_app
        # this will share authentication cookies
        if isinstance(shared_app, __class__):
            self.auth_service = self.CAS(shared_app.username, 
                                         shared_app.password, 
                                         shared_app=self)
        if username and password: 
            self.auth_service = self.CAS(username, 
                                         password, shared_app=self)

    def request(self, method, base, endpoint, **kwargs):
        """
        See UCDavisApplication for main functionality
        Ensures user is authenticated before returning response
        Parameters:
            See UCDavisApplication.get
        """
        r = super(__class__, self).request(method, base, endpoint, **kwargs)

        if 'cas.ucdavis' not in r.url:
            # already authed
            return r
        else:
            # re-auth then send request again
            self.auth_service.auth()
            return super(__class__, self).request(method, base, endpoint, **kwargs)

    class CAS(UCDavisApplication):
        BASE='https://cas.ucdavis.edu'
        LOGIN_ENDPOINT='/cas/login'
        def __init__(self, username, password, shared_app):
            super(__class__, self).__init__(shared_app=shared_app)

            self.username = username
            self.password = password

        def auth(self):
            auth_page = self.get(self.LOGIN_ENDPOINT)
            if '<div id="msg" class="success"' in auth_page.text:
                return # already logged in

            soup = BeautifulSoup(auth_page.text)
            login_form = soup.find("form", id="fm1")

            data = dict()
            # Make sure to submit hidden fields
            for child in login_form.find_all(text=False):
                if child.has_attr('name') and child.has_attr('value'):
                    data[child['name']] = child['value']

            data['username'] = self.username
            data['password'] = self.password

            r = self.post(login_form['action'], data=data)
            if '<div id="msg" class="success"' not in r.text:
                raise InvalidLoginError()
        
"""
Sisweb 
"""
class Sisweb(UCDavisProtectedApplication):
    """
    Wrapper for UC Davis Student Information Service
    http://sisweb.ucdavis.edu/
    """
    BASE='https://sisweb.ucdavis.edu/owa_service/owa'
    MAIN_MENU_ENDPOINT='/twbkwbis.P_GenMenu?name=bmenu.P_MainMnu'
    GRADE_TERM_SELECT_ENDPOINT='/bwskogrd.P_ViewTermGrde'
    GRADE_ENDPOINT='/bwskogrd.P_ViewGrde'
    REGISTRATION_TERM_SELECT_ENDPOINT='/bwskflib.P_SelDefTerm'
    REGISTRATION_TERM_STORE_ENDPOINT='/bwcklibs.P_StoreTerm'
    COURSE_SCHEDULE_ENDPOINT='/bwskfshd.P_CrseSchdDetl'

    def __init__(self, *args, **kwargs):
        super(__class__, self).__init__(*args, **kwargs)
    
    # @property
    # def base(self):
    #     return 'https://sisweb.ucdavis.edu/owa_service/owa'

    def request(self, method, base, endpoint, **kwargs):
        """
        Functionality identical to UCDavisProtectedApplication.request
        except ensures session ID is set before returning response
        Parameters:
            see UCDavisApplication.request
        """
        r = super(__class__, self).request(method, base, endpoint, **kwargs)

        # Sisweb redirects to main menu when session ID is expired
        # If the corresponding <meta> exists, fetch page again as session ID is now set. 
        if re.search('<meta http-equiv="refresh" content="0;'
                     'url=.*{}'.format(re.escape(self.MAIN_MENU_ENDPOINT)),
                     r.text):
            return super(__class__, self).request(method, base, endpoint, **kwargs)
        else:
            return r

    def _check_term(self, term):
        if not isinstance(term, Term):
            raise ValueError("provided term not an instance of Term class")

    def _term_option_exists(self, text, term):
        """
        Returns boolean representing if term option exists within
        <select id="term_id"> dropdown in text.

        Parameters:
            text: html content of term select page
            term: Term object
        """
        soup = BeautifulSoup(text)
        term_select_ele = soup.find("select", id="term_id") 
        term_options = [o['value'] for o in term_select_ele.find_all("option")]
        if str(term) not in term_options:
            return False

        return True

    def _term_list(self, text):
        """
        Returns list of Term for term options listed inside <select id="term_id">
        element of text, which is present at REGISTRATION_TERM_SELECT_ENDPOINT and
        GRADE_TERM_SELECT_ENDPOINT
        Parameters:
            text: HTML page containing tag <select id="term_id">
        """
        soup = BeautifulSoup(text)
        term_select_ele = soup.find("select", id="term_id") 
        term_options = [o['value'] for o in term_select_ele.find_all("option")]
        
        terms = list()
        for term in term_options:
            # '201410' -> Term('2014', '10')
            terms.append(Term(term[0:4], term[4:]))

        return terms

    def terms_enrolled(self):
        """
        Returns list of Term for all terms in which student has enrolled
        """
        r = self.get(self.REGISTRATION_TERM_SELECT_ENDPOINT)
        return self._term_list(r.text)

    def terms_completed(self):
        """
        Returns list of Term for all terms completed by student
        """
        r = self.get(self.GRADE_TERM_SELECT_ENDPOINT)
        return self._term_list(r.text)

    def courses_enrolled(self, term):
        """
        Returns a list of course reference numbers for 
        enrolled courses in the given term
        Parameters:
            term: Term object
        """
        self._check_term(term) 

        # Select Term
        r = self.get(self.REGISTRATION_TERM_SELECT_ENDPOINT)
        if term not in self._term_list(r.text):
            raise ValueError("Invalid term: User does not have enrollment "
                             "information available for {}".format(term.name))
        data = {'term_in': str(term)}
        r = self.post(self.REGISTRATION_TERM_STORE_ENDPOINT, 
                      data=data)

        # Fetch course list
        r = self.get(self.COURSE_SCHEDULE_ENDPOINT)
        soup = BeautifulSoup(r.text)
        course_tables = soup.find_all("table", 
                                      class_="datadisplaytable", 
                                      attrs={"summary": re.compile(".*course detail$")})

        crns = list()
        for table in course_tables:
            rows = table.find_all('tr')
            crn_row = rows[1]
            crns.append(crn_row.find('td').string)

        return crns

    def grades(self, term):
        """
        Returns grades for given term as dictionary
        Parameters: 
            term: Term object
        """
        self._check_term(term)

        # check if grades available for provided term
        r = self.get(self.GRADE_TERM_SELECT_ENDPOINT)
        if term not in self._term_list(r.text):
            raise ValueError("User does not have final grades available for {}".format(term.name))

        # fetch grades page
        data = {'term_in': str(term)}
        r = self.post(self.GRADE_ENDPOINT, data=data)
        soup = BeautifulSoup(r.text)

        course_table = None
        # loop until correct table is found
        for table in soup.find_all('table', class_='datadisplaytable'):
            caption = table.find('caption')
            if (caption and 
               caption.string == "Undergraduate Level - Qtr. Course work"):
                course_table = table
                break

        if not course_table:
            raise MalformedPageError("expected undergraduate course work"
                                     "table on page {}".format(r.url))

        # Extract grades from page
        course_header_row = course_table.find('tr')
        grades = dict()

        for course_row in course_header_row.find_next_siblings('tr'):
            cells = course_row.find_all('td')
            cell_strings = [c.string.strip() for c in cells]
            crn = cell_strings[0]
            grades[crn] = dict()
            grades[crn]['letter'] = cell_strings[5]
            grades[crn]['units_enrolled'] = float(cell_strings[6])
            grades[crn]['units_completed'] = float(cell_strings[7])
            grades[crn]['units_attempted'] = float(cell_strings[8])
            grades[crn]['grade_points'] = float(cell_strings[9])

        return grades

"""
University Registrar
"""
class Course(object):
    """
    Container for course information
    """
    _attrs = ['course_name', 'section', 'course_title', 
              'instructor', 'subject', 'ge_credit', 'available_seats', 
              'max_enrollment', 'meetings', 'description',  'final_exam', 'drop_time']

    def __init__(self, crn, term, **attrs):
        """
        Parameters:
            crn: five-digit course reference number
            term: Term object
        """
        self.crn = crn
        self.term = term
        
        i = 0     
        for k,v in attrs.items():
            if k in self._attrs:
                setattr(self, k, v)
                i += 1
        
        if i != len(self._attrs): # If not all attributes provided in kwargs
            course_complete = Registrar.get_course(crn) # fetch rest of course detail
            self.__dict__ = course_complete.__dict__.copy()

    def __str__(self):
        return '{} - {} - {}'.format(self.term, self.course_name, self.course_title)

    def __eq__(self, other):
        return self.crn == other.crn and self.term == other.term

class InvalidCrnOrTermError(Exception):
    pass

class QueryError(Exception):
    pass

class Registrar(UCDavisApplication):

    """
    Wrapper for university registrar
    http://registrar.ucdavis.edu/
    """
    BASE='https://registrar.ucdavis.edu'
    COURSE_DETAIL_ENDPOINT='/courses/search/course.cfm'
    COURSE_SEARCH_ENDPOINT='/courses/search/course_search_results_mod8.cfm'

    # @property
    # def base(self):
    #     """
    #     Required base attribute for classes deriving from UCDavisApplication
    #     """
    #     return 'https://registrar.ucdavis.edu'

    def course_detail(self, crn, term):
        """
        Searches for course with given crn and returns Course object
        Parameters:
            crn: course reference number
            term: Term object
        """
        params = {'crn': crn,
                  'termCode': str(term)}

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
            level: CourseQueryOptions.Levels
            units: int in [1,9]
            only_virtual: boolean
            ge_credit: [CourseQueryOptions.GECredit, ...]
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
        params['termYear'], params['term'] = term.year, term.session
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
        course_attrs = dict()

        header = soup.find('h1')
        course_attrs['course_name'] = header.find('strong').string
        course_attrs['course_title'] = header.contents[1][3:]
        course_attrs['section'] = course_attrs['course_name'].split(' ')[2] 
        course_attrs['ge_credit'] = list()

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
                    course_attrs['subject'] = cell.contents[1]

                elif item == 'Instructor:':
                    course_attrs['instructor'] = cell.contents[4]

                elif item == 'Units: ':
                    course_attrs['units'] = cell.contents[2]

                elif 'New GE Credit' in item:
                    for ge_content in cell.contents[1:]:
                        if isinstance(ge_content, str) and len(ge_content):
                            course_attrs['ge_credit'].append(ge_content)

                elif item == 'Available Seats:':
                    course_attrs['available_seats'] = cell.contents[1]

                elif item == 'Maximum Enrollment:':
                    course_attrs['max_enrollment'] = cell.contents[1]

                elif item == 'Final Exam:':
                    date = '{0} {1}'.format(term.year, ' '.join(cell.contents[1].split())) 
                    course_attrs['final_exam'] = datetime.datetime.strptime(date, '%Y %A, %B %d at %I:%M %p')

                elif item == 'Description:':
                    course_attrs['description'] = cell.contents[3]

                elif item == 'Course Drop:':
                    course_attrs['drop_time'] = cell.contents[1]

        # Meeting times
        course_attrs['meetings'] = list()
        meetings_table = soup.find_all('table')[1]
        meeting_rows = meetings_table.find_all('tr')[1:] # all rows after the header
        for row in meeting_rows:
            cells = row.find_all('td')
            day, hours, location = cells
            course_attrs['meetings'].append( (day.contents, hours.contents, location.contents) )

        return course_attrs

    class QueryOptions(object):
        class GECredit(Enum):
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

"""
Schedule Builder
"""
class ScheduleBuilder(UCDavisProtectedApplication):
    pass
"""
davislib.models

This module contains important objects.
"""
import requests
import re
import datetime
from bs4 import BeautifulSoup, element
from enum import Enum

"""
Data containers
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

class Term(object):
    """
    Container for term information
    """
    SESSION_MAPPINGS = {'fall': Session.FALL_QUARTER,
                        'fall semester': Session.FALL_SEMESTER,
                        'summer 2': Session.SUMMER_SESSION_2,
                        'summer special': Session.SUMMER_SPECIAL,
                        'summer 1': Session.SUMMER_SESSION_1,
                        'spring': Session.SPRING_QUARTER,
                        'spring semester': Session.SPRING_SEMESTER,
                        'winter': Session.WINTER_QUARTER}

    def __init__(self, year, session):
        """
        Parameters:
            year:
                e.g. 2014
            session: string or Session object
                valid strings:
                'fall' -> Fall quarter
                'fall semester' -> Fall semester
                'summer 2' -> Second summer session
                'summer special' -> Special summer session
                'summer 1' -> first summer session
                'spring' -> spring quarter
                'spring semeseter' -> spring semester
                'winter' -> winter quarter
        """
        # Maps session string to Session object
        session = self.SESSION_MAPPINGS.get(session, session)
        self.session = self.Session(session)
        self.year = int(year)

    @property
    def code(self):
        """
        Returns term code, used by applications to identify term
        e.g. 201510
        """
        return '{0}{1}'.format(self.year, self.session.value)

    def __str__(self):
        return '{0} {1}'.format(self.session, self.year)

    def __repr__(self):
        return '<Term {}>'.format(self.code)

    def __eq__(self, other):
        return isinstance(other, Term) and str(self.year) == str(other.year) and self.session == other.session

Term.Session = Session # backwards compatibility

class Course(object):
    """
    Container for course information
    """
    _attrs = ['name',
            'number',
            'section',
            'title',
            'units',
            'instructor',
            'subject',
            'ge_areas',
            'available_seats',
            'max_enrollment',
            'meetings',
            'description',
            'final_exam',
            'drop_time']

    def __init__(self, crn, term, **attrs):
        """
        Parameters:
            crn: five-digit course reference number
            term: Term object
            attrs: Attributes prepared in Registrar
        """
        #: Course reference number
        #: e.g. 74382
        self.crn = crn

        #: Course term object
        #: e.g. <Term 201410>
        self.term = term

        #: Course name string
        #: e.g. 'ECS 040'

        self.name = attrs.get('name', None)

        #: Course number
        #: e.g. '040'
        self.number = attrs.get('number', None)

        #: Section code string
        #: e.g. 'A01'
        self.section = attrs.get('section', None)

        #: Course title string
        #: e.g. 'Intro to Programming'
        self.title = attrs.get('title', None)

        #: Number of units, scalar float or tuple (low, hi)
        #: e.g. 2.5 or (1.0,5.0)
        self.units = attrs.get('units', None)

        #: Instructor name string
        #: e.g. 'Sean Davis'
        self.instructor = attrs.get('instructor', None)

        #: Instructor email address
        #: e.g. 'bob@ucdavis.edu'
        self.instructor_email = attrs.get('instructor_email', None)

        #: Instructor consent required, boolean or None
        self.instructor_consent_required = attrs.get('instructor_consent_required', None)

        #: Subject code
        #: e.g. 'ECS'
        self.subject_code = attrs.get('subject_code', SUBJECT_CODES_BY_NAME.get(attrs.get('subject')))

        #: Subject name string
        #: e.g. 'Engineering Computer Science'
        self.subject = attrs.get('subject', SUBJECT_NAMES_BY_CODE.get(self.subject_code))

        #: List of GE credit satisfied
        #: e.g. ['Arts & Humanities', 'Oral Literacy']
        self.ge_areas = attrs.get('ge_areas', list())

        #: Number of available seats
        #: e.g. 30
        self.available_seats = attrs.get('available_seats', None)

        #: Maximum enrollment number
        #: e.g. 99
        self.max_enrollment = attrs.get('max_enrollment', None)

        #: (Sisweb only)
        self.wl_capacity = attrs.get('wl_capacity', None)

        #: (Sisweb / ScheduleBuilder only)
        self.wl_length = attrs.get('wl_length', None)

        #: (Sisweb only)
        self.xl_capacity = attrs.get('xl_capacity', None)

        #: (Sisweb only)
        self.xl_length = attrs.get('xl_length', None)

        #: Meetings, as list of meetings represented as dictionaries
        #: e.g. [
        #:        {'days': 'TR', 'times': (start timedelta from midnight, end timedelta from midnight), 'location': 'Storer Hall 1322', 'type': None or 'LEC' or 'DIS'}]
        #:        ...
        #:      ]
        self.meetings = attrs.get('meetings', None)

        #: Course description string
        self.description = attrs.get('description', None)

        #: Final exam time, as datetime.datetime object
        #: or string 'See Instructor'
        self.final_exam = attrs.get('final_exam', None)

        #: Drop time string
        #: e.g. '20 Day Drop'
        self.drop_time = attrs.get('drop_time', None)

        #: Prerequesite string
        #: e.g. 'course 40 and 60'
        self.prerequisites = attrs.get('prerequisites', None)

    def __str__(self):
        return '{}: {} -- CRN {} ({})'.format(self.name,
                                               self.title,
                                               self.crn,
                                               self.term)

    def __repr__(self):
        return '<Course {} ({})>'.format(self.crn, repr(self.term))

    def __eq__(self, other):
        return isinstance(other, Course) and self.crn == other.crn and self.term == other.term

"""
Applications
"""

class InvalidLoginError(Exception):
    pass

class Application(object):
    """
    Base class for UC Davis web app
    """
    USER_AGENT=('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537'
                '.36 (KHTML, like Gecko) Chrome/40.0.2214.115 Safari/537.36')

    def __init__(self, shared_app=None):
        """
        Parameters:
            (optional) shared_app: object deriving from Application
                                   whose session will be used in new object
                                   (Specify this parameter if you wish to share cookies)
        """
        super(Application, self).__init__()

        if shared_app:
            if isinstance(shared_app, __class__):
                self.s = shared_app.s
            else:
                raise ValueError("shared_app does not derive from Application")
        else:
            self.s = requests.Session()
            self.s.headers.update({'User-Agent': self.USER_AGENT})

    def request(self, method, base, endpoint, **kwargs):
        return self.s.request(method, ''.join([base, endpoint]), **kwargs)

    def get(self, *args, **kwargs):
        """
        Executes GET request on application BASE at endpoint
        Parameters:
            see Application.request
        """
        return self.request('get', self.__class__.BASE, *args, **kwargs)

    def post(self, *args, **kwargs):
        """
        Executes POST request on application BASE at endpoint
        Parameters:
            see Application.request
        """
        return self.request('post', self.__class__.BASE, *args, **kwargs)

class ProtectedApplication(Application):
    """
    Base class for UC Davis web app relying on CAS (central authentication service)
    """
    def __init__(self, username, password, shared_app=None):
        """
        Parameters:
            username: kerberos login id
            password: kerberos password
            (optional) shared_app: object deriving from Application
                                   whose session will be shared with self.
                                   if derives from ProtectedApplication,
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
        See Application for main functionality
        Ensures user is authenticated before returning response
        Parameters:
            See Application.get
        """
        r = super(__class__, self).request(method, base, endpoint, **kwargs)

        if 'cas.ucdavis' not in r.url:
            # already authed
            return r
        else:
            # re-auth then send request again
            self.auth_service.auth()
            return super(__class__, self).request(method, base, endpoint, **kwargs)

    class CAS(Application):
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

            soup = BeautifulSoup(auth_page.text, 'html.parser')
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

SUBJECT_CODES_BY_NAME = {
    'African American & African Std': 'AAS',
    'Agric Mngt & Range Resources': 'AMR',
    'Agricultural & Envir Chem Grad': 'AGC',
    'Agricultural & Resource Econ': 'ARE',
    'Agricultural Economics': 'AGE',
    'Agricultural Education': 'AED',
    'Agricultural Systems & Envir': 'ASE',
    'Agronomy': 'AGR',
    'American Studies': 'AMS',
    'Animal Behavior (Graduate Gp)': 'ANB',
    'Animal Biology': 'ABI',
    'Animal Biology Grad Gp': 'ABG',
    'Animal Genetics': 'ANG',
    'Animal Science': 'ANS',
    'Anthropology': 'ANT',
    'Applied Behavioral Sciences': 'ABS',
    'Applied Biological System Tech': 'ABT',
    'Arabic': 'ARB',
    'Art History': 'AHI',
    'Art Studio': 'ART',
    'Asian American Studies': 'ASA',
    'Astronomy': 'AST',
    'Atmospheric Science': 'ATM',
    'Avian Sciences': 'AVS',
    'Bio, Molec, Cell, Dev Bio GG': 'BCB',
    'Biochemistry & Molec Biol Grad': 'BMB',
    'Biological Sciences': 'BIS',
    'Biophotonics': 'BPT',
    'Biophysics (Graduate Group)': 'BPH',
    'Biostatistics': 'BST',
    'Biotechnology': 'BIT',
    'Biotechnology (Desig Emphasis)': 'DEB',
    'Cantonese': 'CAN',
    'Cell & Developmental Biol Grad': 'CDB',
    'Celtic': 'CEL',
    'Chemistry': 'CHE',
    'Chicano Studies': 'CHI',
    'Chinese': 'CHN',
    'Cinema & Technocultural Stud': 'CTS',
    'Cinema and Digital Media': 'CDM',
    'Classics': 'CLA',
    'Clinical Research': 'CLH',
    'Colleges at La Rue': 'CLR',
    'Communication': 'CMN',
    'Community & Regional Develpmnt': 'CRD',
    'Comparative Literature': 'COM',
    'Consumer Economics': 'CNE',
    'Consumer Sciences': 'CNS',
    'Critical Theory (Desig Emphas)': 'CRI',
    'Croatian': 'CRO',
    'Crop Science & Management': 'CSM',
    'Cultural Studies': 'CST',
    'Danish': 'DAN',
    'Design': 'DES',
    'Dramatic Art': 'DRA',
    'East Asian Studies': 'EAS',
    'Ecology': 'ECL',
    'Economics': 'ECN',
    'Economy, Justice & Society': 'EJS',
    'Education': 'EDU',
    'Education Abroad Program': 'EAP',
    'Endocrinology (Graduate Group)': 'EDO',
    'Engineering': 'ENG',
    'Engineering Aerospace Sci': 'EAE',
    'Engineering Applied Sci-Davis': 'EAD',
    'Engineering Applied Sci-Lvrmor': 'EAL',
    'Engineering Biological Systems': 'EBS',
    'Engineering Biomedical': 'BIM',
    'Engineering Chemical': 'ECH',
    'Engineering Chemical-Materials': 'ECM',
    'Engineering Civil & Environ': 'ECI',
    'Engineering Computer Science': 'ECS',
    'Engineering Electrical & Compu': 'EEC',
    'Engineering Materials Science': 'EMS',
    'Engineering Mechanical': 'EME',
    'Engineering Mechanical & Aero': 'MAE',
    'English': 'ENL',
    'Entomology': 'ENT',
    'Environmental Horticulture': 'ENH',
    'Environmental Plan & Managemnt': 'ENP',
    'Environmental Resource Science': 'ERS',
    'Environmental Sci & Management': 'ESM',
    'Environmental Science & Policy': 'ESP',
    'Environmental Studies': 'EST',
    'Environmental Toxicology': 'ETX',
    'Epidemiology (Graduate Group)': 'EPI',
    'Evolution and Ecology': 'EVE',
    'Exercise Biology': 'EXB',
    'Exercise Science': 'EXS',
    'Fiber And Polymer Science': 'FPS',
    'Film Studies': 'FMS',
    'Food Science & Technology': 'FST',
    'Food Service Management': 'FSM',
    'Forensic Science': 'FOR',
    'French': 'FRE',
    'Freshman Seminar': 'FRS',
    'Genetics (Graduate Group)': 'GGG',
    'Geography': 'GEO',
    'Geology': 'GEL',
    'German': 'GER',
    'Global Disease Biology': 'GDB',
    'Greek': 'GRK',
    'Health Informatics': 'MHI',
    'Hebrew': 'HEB',
    'Hindi/Urdu': 'HIN',
    'History': 'HIS',
    'History & Philosophy of Sci.': 'HPS',
    'Honors Challenge': 'HNR',
    'Horticulture': 'HRT',
    'Human Development': 'HDE',
    'Human Rights': 'HMR',
    'Humanities': 'HUM',
    'Hungarian': 'HUN',
    'Hydrologic Science': 'HYD',
    'Immunology (Graduate Group)': 'IMM',
    'Integrated Pest Management': 'IPM',
    'Integrated Studies': 'IST',
    'International Agricultural Dev': 'IAD',
    'International Commercial Law': 'ICL',
    'International Relations': 'IRE',
    'Italian': 'ITA',
    'Japanese': 'JPN',
    'Jewish Studies': 'JST',
    'Landscape Architecture': 'LDA',
    'Latin': 'LAT',
    'Latin American & Hemispheric': 'LAH',
    'Law': 'LAW',
    'Linguistics': 'LIN',
    'Management': 'MGT',
    'Management Work Prof Bay Area': 'MGB',
    'Management Working Professionl': 'MGP',
    'Master of Public Health': 'MPH',
    'Math & Physical Sci': 'MPS',
    'Mathematics': 'MAT',
    'Med - Anesthesiology': 'ANE',
    'Med - Biological Chemistry': 'BCM',
    'Med - Cell Biol & Human Anat': 'CHA',
    'Med - Clinical Psychology': 'CPS',
    'Med - Community & Intl Health': 'CMH',
    'Med - Dermatology': 'DER',
    'Med - Epidemiology & Prev Med': 'EPP',
    'Med - Family Practice': 'FAP',
    'Med - Human Physiology': 'HPH',
    'Med - Internal Medicine': 'IMD',
    'Med - Intrl: Cardiology': 'CAR',
    'Med - Intrl: Clinic Nutr&Metab': 'NCM',
    'Med - Intrl: Emergency Med': 'EMR',
    'Med - Intrl: Endocrinol &Metab': 'ENM',
    'Med - Intrl: Gastroenterology': 'GAS',
    'Med - Intrl: General Medicine': 'GMD',
    'Med - Intrl: Hematology-Oncol': 'HON',
    'Med - Intrl: Infectious Dis': 'IDI',
    'Med - Intrl: Nephrology': 'NEP',
    'Med - Intrl: Pulmonary': 'PUL',
    'Med - Medical Microbiology': 'MMI',
    'Med - Medical Pharmacol &Toxic': 'PHA',
    'Med - Medical Science': 'MDS',
    'Med - Neurology': 'NEU',
    'Med - Neurosurgery': 'NSU',
    'Med - Obstetrics & Gynecology': 'OBG',
    'Med - Occupational &Envrn Hlth': 'OEH',
    'Med - Ophthalmology': 'OPT',
    'Med - Orthopaedic Surgery': 'OSU',
    'Med - Otolaryngology': 'OTO',
    'Med - Pathology': 'PMD',
    'Med - Pediatrics': 'PED',
    'Med - Physical Medicine &Rehab': 'PMR',
    'Med - Plastic Surgery': 'PSU',
    'Med - Psychiatry': 'PSY',
    'Med - Public Health Sciences': 'SPH',
    'Med - Radiation Oncology': 'RON',
    'Med - Radiology (Diagnostic)': 'RDI',
    'Med - Radiology-Nuclear Med': 'RNU',
    'Med - Rheumatology (Allergy)': 'RAL',
    'Med - Surgery': 'SUR',
    'Med - Urology': 'URO',
    'Medical Informatics': 'MDI',
    'Medieval Studies': 'MST',
    'Microbiology': 'MIC',
    'Microbiology (Graduate Group)': 'MIB',
    'Middle East/South Asian Std': 'MSA',
    'Military Science': 'MSC',
    'Molecular and Cellular Biology': 'MCB',
    'Molecular, Cell & Int Physio': 'MCP',
    'Music': 'MUS',
    'Native American Studies': 'NAS',
    'Nature and Culture': 'NAC',
    'Nematology': 'NEM',
    'Neurobiology, Physio & Behavior': 'NPB',
    'Neuroscience (Graduate Group)': 'NSC',
    'Nursing': 'NRS',
    'Nutrition': 'NUT',
    'Nutrition Graduate Group': 'NGG',
    'Nutritional Biology (Grad Grp)': 'NUB',
    'Performance Studies (Grad Grp)': 'PFS',
    'Pharmacology-Toxicology (Grad)': 'PTX',
    'Philosophy': 'PHI',
    'Physical Education': 'PHE',
    'Physician Assistant Studies': 'PAS',
    'Physics': 'PHY',
    'Physiology Graduate Group': 'PGG',
    'Plant Biology': 'PLB',
    'Plant Biology (Graduate Group)': 'PBI',
    'Plant Pathology': 'PLP',
    'Plant Protection & Pest Mangmt': 'PPP',
    'Plant Science': 'PLS',
    'Political Science': 'POL',
    'Pomology': 'POM',
    'Population Biology': 'PBG',
    'Portuguese': 'POR',
    'Professional Accountancy': 'ACC',
    'Psychology': 'PSC',
    'Range Science': 'RMT',
    'Religious Studies': 'RST',
    'Russian': 'RUS',
    'School of Veterinary Medicine': 'VET',
    'Science & Technology Studies': 'STS',
    'Science and Society': 'SAS',
    'Short-Term Abroad Program': 'STP',
    'Social Theory & Compar History': 'STH',
    'Sociology': 'SOC',
    'Soil Science': 'SSC',
    'Spanish': 'SPA',
    'Statistics': 'STA',
    'Study of Religion': 'REL',
    'Sustainable Ag & Food Sys': 'SAF',
    'Technocultural Studies': 'TCS',
    'Textiles & Clothing': 'TXC',
    'Transportation Tech & Policy': 'TTP',
    'Turkish': 'TSK',
    'University Writing Program': 'UWP',
    'Urdu': 'URD',
    'Vegetable Crops': 'VCR',
    'Veterinary Clinical Rotation': 'DVM',
    'Veterinary Medicine': 'VMD',
    'Viticulture & Enology': 'VEN',
    'VM Anatomy, Physiol & Cell Bio': 'APC',
    'VM Medicine and Epidemiology': 'VME',
    'VM Molecular Biosciences': 'VMB',
    'VM Pathology, Microbiol &Immun': 'PMI',
    'VM Population Health & Reprod': 'PHR',
    'VM Preventive Veterinary Med': 'MPM',
    'VM Surgical & Radiological Sci': 'VSR',
    'Wildlife, Fish & Conserv Biol': 'WFC',
    'Women\'s Studies': 'WMS',
    'Workload': 'WLD'
}

SUBJECT_NAMES_BY_CODE = {code: name for name, code in SUBJECT_CODES_BY_NAME.items()}
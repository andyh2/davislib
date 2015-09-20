"""
davislib.sisweb

This moduile provides an interface to the UC Davis Student Information service
"""
from .models import ProtectedApplication, Term
from bs4 import BeautifulSoup
import requests
import re

class Sisweb(ProtectedApplication):
    """
    This class provides an interface to the UC Davis Student Information Service
    http://sisweb.ucdavis.edu/
    """
    BASE='https://sisweb.ucdavis.edu/owa_service/owa'
    MAIN_MENU_ENDPOINT='/twbkwbis.P_GenMenu?name=bmenu.P_MainMnu'
    GRADE_TERM_SELECT_ENDPOINT='/bwskogrd.P_ViewTermGrde'
    GRADE_ENDPOINT='/bwskogrd.P_ViewGrde'
    REGISTRATION_TERM_SELECT_ENDPOINT='/bwskflib.P_SelDefTerm'
    REGISTRATION_TERM_STORE_ENDPOINT='/bwcklibs.P_StoreTerm'
    COURSE_SCHEDULE_ENDPOINT='/bwskfshd.P_CrseSchdDetl'

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
        if re.search('<meta http-equiv="refresh" content="0;url=.*', r.text):
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
        soup = BeautifulSoup(text, 'html.parser')
        term_select_ele = soup.find("select", id="term_id")
        term_options = [o['value'] for o in term_select_ele.find_all("option")]
        if term.code not in term_options:
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
        soup = BeautifulSoup(text, 'html.parser')
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
                             "information available for {}".format(term))
        data = {'term_in': term.code}
        r = self.post(self.REGISTRATION_TERM_STORE_ENDPOINT, 
                      data=data)

        # Fetch course list
        r = self.get(self.COURSE_SCHEDULE_ENDPOINT)
        soup = BeautifulSoup(r.text, 'html.parser')
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
            raise ValueError("User does not have final grades available for {}".format(term))

        # fetch grades page
        data = {'term_in': term.code}
        r = self.post(self.GRADE_ENDPOINT, data=data)
        soup = BeautifulSoup(r.text, 'html.parser')

        course_table = None
        # loop until correct table is found
        for table in soup.find_all('table', class_='datadisplaytable'):
            caption = table.find('caption')
            if (caption and 
               caption.string == "Undergraduate Level - Qtr. Course work"):
                course_table = table
                break

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

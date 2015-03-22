"""
Calculates number of units required to satisfy the 
UC Davis General Education Requirement
http://catalog.ucdavis.edu/ugraded/gereqt.html

Author: Andy Haden
"""
import getpass
import itertools
from davislib import Sisweb, Registrar, Term

CAT_MINIMUMS = {'Topical Breadth': 52, 
                'Core Literacies': 35}

AREA_MINIMUMS = {
    'Arts & Humanities': (12, 20),
    'Science & Engineering': (12, 20),
    'Social Sciences': (12, 20),
    # 'English Composition': 8, (this requirement differs by college)
    'Writing Experience': 6,
    'Oral Literacy': 3,
    'Visual Literacy': 3,
    'American Culture, Government, and History': 6,
    'World Cultures': 3,
    'Quantitative Literacy': 3,
    'Scientific Literacy': 3
}

GE_AREAS = {
    'Topical Breadth': [
        'Arts & Humanities', 
        'Science & Engineering', 
        'Social Sciences'],
    'Core Literacies': [
       # 'English Composition', (this requirement differs by college)
       'Writing Experience',
       'Oral Literacy',
       'Visual Literacy',
       'American Culture, Government, and History',
       'World Cultures',
       'Quantitative Literacy',
       'Scientific Literacy']
}

def category_conflicts(course):
    """
    Returns list of GE category names
    if course satisfies more than one area inside one of those categories.
    A completed course of this nature may only count towards one area within the category.
    """
    cat_found = dict.fromkeys(GE_AREAS.keys(), False)
    conflicts = list()

    for area in course.ge_areas:
        for cat, areas in GE_AREAS.items():
            if cat not in conflicts and area in areas:
                if cat_found[cat] == 1:
                    conflicts.append(cat)
                else:
                    cat_found[cat] = 1

    return conflicts

def pretty_number(num):
    """
    Returns formatted number as follows:
    If num's only decimal place is zero, return integer representation. 
    Otherwise, round to two decimal places.
    Parameters:
        num: Number
    """
    return str(round(num, 2) if num % 1 else int(num))    

def print_results(area_credit):
    """
    Parameters: 
        area_credit: dictionary containing completed units by GE area
                     i.e. {'Arts & Humanitites': 0.0, ...}
    """
    print("Additional units required for graduation")
    print("(by GE category and area)")
    print()

    for category, areas in GE_AREAS.items():
        cat_sum = sum([units for area, units in area_credit.items()
                       if area in GE_AREAS[category]])
        cat_more = CAT_MINIMUMS[category] - cat_sum
        if cat_more < 0:
            cat_more = 0 

        print('{}: {} more units required'.format(category, 
                                                  pretty_number(cat_more)))

        for area in areas:
            print("    {}: ".format(area), end="")
            
            area_min = AREA_MINIMUMS[area]
            if type(area_min) is tuple:
                low = area_min[0] - area_credit[area]
                hi = area_min[1] - area_credit[area]
                if low < 0:
                    low = 0
                if hi < 0:
                    hi = 0
                if hi > 0:
                    print("{} to {}".format(pretty_number(low), 
                                            pretty_number(hi)), 
                          end="")
                else:
                    print("0")
            else:
                more = area_min - area_credit[area]
                if more < 0:
                    more = 0
                print(pretty_number(more), end="")

            print(" more units")

def fix_conflicts(area_credit, flagged):
    """
    For each flagged course, adds its credit to credit area
    in which student has least credit. 

    If a course satisfies credit in more than one GE category
    (Topical Breadth, Core Literacies), then the credit
    can only be applied to *one* area within the category.

    Parameters: 
        area_credit: dictionary containing units completed 
                     by area
                     {'area name': units completed} 
        flagged: dictionary containing courses with 
                     conflicting credit by category
                     {'category': [Course c, ...]}
    """
    for (category, courses) in flagged.items():
        for course in courses:
            conflicts = [area for area in course.ge_areas if area
                         in GE_AREAS[category]]
            min_ = conflicts[0]
            for (area, units) in area_credit.items():
                if area in conflicts and units < area_credit[min_]:
                    min_ = area
            area_credit[min_] += course.units

def add_term_credit(area_credit, flagged, sw, reg, term):
    """
    Iterating through each course completed in term, 
    compiles and adds accumulated GE credit to area_credit.

    If a course satisfies credit in more than one GE category
    (Topical Breadth, Core Literacies), then that course is
    added to the flagged dictionary. 

    Parameters:
        area_credit: dictionary containing completed units by GE area
                     i.e. {'Arts & Humanitites': 0.0, ...} 
        flagged: dictionary containing conflicting courses by GE category
                     i.e. {'Topical Breadth': [<Course>, ...], 
                           'Core Literacies': []}
        sw: Sisweb object
        reg: Registrar object
        term: Term object
    """
    term_grades = sw.grades(term)

    for (crn, grades) in term_grades.items():
        if grades['units_completed'] > 0:
            course = reg.course_detail(term, crn)
            cat_conflicts = category_conflicts(course)
            for cat in cat_conflicts:
                flagged[cat].append(course)

            for area in course.ge_areas:
                if area in area_credit.keys():
                    conflict_area_nested = [GE_AREAS[cat] for cat in cat_conflicts]
                    conflict_areas = itertools.chain.from_iterable(conflict_area_nested)

                    if area in conflict_areas:
                        continue
                    area_credit[area] += float(grades['units_completed'])

def main():
    username = input("Enter kerberos username: ")
    password = getpass.getpass("Enter kerberos password: ")
    print()

    sw = Sisweb(username, password)
    reg = Registrar()

    terms = sw.terms_completed()
    area_credit = dict.fromkeys(AREA_MINIMUMS.keys(), 0.0)
    flagged = dict.fromkeys(GE_AREAS.keys(), list())

    for term in terms:
        add_term_credit(area_credit, flagged, sw, reg, term)

    fix_conflicts(area_credit, flagged)
    print_results(area_credit)

if __name__ == '__main__':
    main()
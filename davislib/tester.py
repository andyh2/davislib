from davislib import Registrar, Term
r = Registrar()
term = Term(2013, Term.Session.SPRING_QUARTER)

with open('subjects.txt') as f:
    for sub in f:
        crns = r.course_query(term, subject=sub)
        for crn in crns:
            print('fetching {}'.format(crn))
            r.course_detail(term, crn)

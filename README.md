# davislib

A Python interface to online UC Davis student services

Requires Python 3

Services currently supported:

- University Registrar
    - Search courses with custom queries
    - Fetch details of specific course
- Sisweb
    - List terms both enrolled and completed
    - List courses enrolled for a given term
    - Fetch final grades for a given term

## Examples
How many more GE units must I take to graduate?
```
Andys-MacBook-Pro:davislib andyh2$ python examples/graduate.py
Enter kerberos username: ahaden
Enter kerberos password:

Additional units required for graduation
(by GE category and area)

Topical Breadth: 44 more units required
    Arts & Humanities: 12 to 20 more units
    Science & Engineering: 4 to 12 more units
    Social Sciences: 12 to 20 more units
Core Literacies: 27 more units required
    Writing Experience: 6 more units
    Oral Literacy: 3 more units
    Visual Literacy: 3 more units
    American Culture, Government, and History: 6 more units
    World Cultures: 3 more units
    Quantitative Literacy: 0 more units
    Scientific Literacy: 3 more units
```

Fetch Term Grades
```python
>>> from davislib import Sisweb, Term
>>> sw = Sisweb("kerberos username", "kerberos password")
>>> term = Term(2014, 'fall')
>>> sw.grades(term)
{'40658': {'units_enrolled': 4.0, 
          'units_attempted': 4.0, 
          'units_completed': 4.0, 
          'grade_points': 13.2, 
          'letter': 'B+'},
 ...
}
```

Who's teaching ECS 60 in the Spring?
```python
>>> from davislib import Registrar, Term
>>> r = Registrar()
>>> term = Term(2015, 'spring')
>>> crns = r.course_query(term, name="ECS 60")
>>> assert len(crns) > 0
>>> course = r.course_detail(term, crns[0])
>>> course.instructor
Sean Davis
```

I'm not a morning person. Which spring ECS classes start after 2pm?
```python
>>> from davislib import Registrar, Term
>>> r = Registrar()
>>> term = Term(2015, 'spring')
>>> crns = r.course_query(term, subject='ECS', start=14)
>>> courses = [r.course_detail(term, crn) for crn in crns]
>>> [course.name for course in courses]
['ECS 030 A02', 'ECS 030 A06', 'ECS 040 A01', 'ECS 050 A01', 'ECS 060 A02', 'ECS 120 001', 'ECS 122A 001', 'ECS 122B 001', 'ECS 153 001', 'ECS 160 001', 'ECS 160 001', 'ECS 251 001']
```

I want a lower division course satisfying Arts & Humanities and Visual Literacy GE credit for the spring. Roll the dice!
```python
>>> import random
>>> from davislib import Registrar, Term
>>> from davislib.registrar import QueryOptions
>>> r = Registrar()
>>> term = Term(2015, 'spring')
>>> ge_areas = [QueryOptions.GEArea.AH, QueryOptions.GEArea.VL]
>>> crns = r.course_query(term, 
...                       level=QueryOptions.Level.LOWER_DIV,
...                       ge_areas=ge_areas)
>>> course = r.course_detail(term, random.choice(crns))
>>> str(course)
'MUS 024C 001: Intro Music History -- CRN 53159 (Spring Quarter 2015)'

```
## Running on CSIF
If you're a Davis CS student, run the following commands on a CSIF computer to install davislib.

```sh
git clone https://github.com/andyh2/davislib.git
cd davislib
python3 setup.py install --user
```
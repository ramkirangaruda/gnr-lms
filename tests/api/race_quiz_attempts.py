"""Reproduces M-2: 20 parallel submits of a 3-attempt quiz, 5 trials (staging only).  python3 tests/api/race_quiz_attempts.py"""
import sys, subprocess, concurrent.futures as cf
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lms import LMS
R=os.environ.get('REPO_DIR', os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
def sh(c): return subprocess.run(['docker','compose','exec','-T','web','python','manage.py','shell','-v0','-c',c],cwd=R,capture_output=True,text=True).stdout.strip()
for trial in range(5):
    sh("from courses.models import *;QuizAttempt.objects.filter(student__username='lt0013',quiz__course__slug='qa-course-3').delete();Quiz.objects.filter(course__slug='qa-course-3').update(max_attempts=3)")
    s=LMS().login('lt0013'); q=sh("from courses.models import Quiz;print(Quiz.objects.get(course__slug='qa-course-3').pk)")
    p=f'/courses/qa-course-3/quizzes/{q}/'; tok=s.csrf(p)
    with cf.ThreadPoolExecutor(20) as ex: list(ex.map(lambda _: s.post(p,{'csrfmiddlewaretoken':tok},form_page=p).status_code, range(20)))
    print('trial',trial,'attempts stored (limit 3):', sh("from courses.models import QuizAttempt;print(QuizAttempt.objects.filter(student__username='lt0013',quiz__course__slug='qa-course-3').count())"))

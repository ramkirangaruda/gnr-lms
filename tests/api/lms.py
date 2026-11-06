"""Tiny HTTP client for the LMS: logs in like a browser (CSRF + session cookie)."""
import os
import re

import requests

BASE = os.environ.get("BASE_URL", "http://localhost").rstrip("/")
PW = os.environ.get("QA_PASSWORD", "QaPass#2026")


class LMS(requests.Session):
    def __init__(self, base=BASE):
        super().__init__()
        self.base = base
        self.headers["User-Agent"] = "gnr-lms-qa"

    def url(self, path):
        return path if path.startswith("http") else self.base + path

    def get(self, path, **kw):
        kw.setdefault("allow_redirects", False)
        return super().get(self.url(path), **kw)

    def csrf(self, path):
        r = super().get(self.url(path))
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
        return m.group(1) if m else self.cookies.get("csrftoken", "")

    def post(self, path, data=None, form_page=None, files=None, **kw):
        data = dict(data or {})
        data.setdefault("csrfmiddlewaretoken", self.csrf(form_page or path))
        kw.setdefault("allow_redirects", False)
        return super().post(self.url(path), data=data, files=files, headers={"Referer": self.url(form_page or path)}, **kw)

    def login(self, username, password=PW):
        r = self.post("/login/", {"username": username, "password": password})
        self.logged_in = r.status_code == 302 and "/login/" not in r.headers.get("Location", "")
        return self

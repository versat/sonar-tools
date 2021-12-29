#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

'''

    Abstraction of the SonarQube "background task" concept

'''

import time
import json
import re
from sonarqube import env
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb
import sonarqube.sqobject as sq
import sonarqube.utilities as util


SUCCESS = 'SUCCESS'
PENDING = 'PENDING'
IN_PROGRESS = 'IN_PROGRESS'
FAILED = 'FAILED'
CANCELED = 'CANCELED'

TIMEOUT = 'TIMEOUT'

STATUSES = (SUCCESS, PENDING, IN_PROGRESS, FAILED, CANCELED)

SUSPICIOUS_EXCLUSIONS = (r'\*\*/[^\/]+/\*\*', r'\*\*\/\*\.\w+')

class Task(sq.SqObject):

    def __init__(self, task_id, endpoint, data=None):
        super().__init__(task_id, endpoint)
        self._json = data
        self._context = None
        self._error = None
        self._type = None
        self._analysis_id = None
        self._submitter = None
        self._status = None
        self._comp_key = None
        self._execution_time = None
        self._submitted_at = None
        self._started_at = None
        self._ended_at = None

    def __str__(self):
        return f"background task '{self.key}'"

    def id(self):
        return self.key

    def wait_for_completion(self, timeout=180):
        wait_time = 0
        sleep_time = 0.5
        params = {'status': ','.join(STATUSES), 'type': self.type()}
        if self.endpoint.version() >= (8, 0, 0):
            params['component'] = self.key
        else:
            params['q'] = self.key
        status = PENDING
        while status not in (SUCCESS, FAILED, CANCELED, TIMEOUT):
            time.sleep(sleep_time)
            wait_time += sleep_time
            sleep_time *= 2
            resp = env.get('ce/activity', params=params, ctxt=self.endpoint)
            for t in json.loads(resp.text)['tasks']:
                if t['id'] != self.key:
                    continue
                status = t['status']
            if wait_time >= timeout and status not in (SUCCESS, FAILED, CANCELED):
                status = TIMEOUT
            util.logger.debug("%s is '%s'", str(self), status)
        return status

    def __load(self):
        if self._json is not None:
            return
        self.__load_context()

    def __load_context(self):
        if self._json is not None and ('scannerContext' in self._json or not self.has_scanner_context()):
            # Context already retrieved or not available
            return
        params = {'id': self.key, 'additionalFields': 'scannerContext,stacktrace'}
        resp = env.get('ce/task', params=params, ctxt=self.endpoint)
        self._json = json.loads(resp.text)['task']

    def has_scanner_context(self):
        self.__load()
        if 'hasScannerContext' in self._json:
            return self._json['hasScannerContext']
        return False

    def type(self):
        self.__load()
        return self._json['type']

    def component(self):
        self.__load()
        return self._json['componentKey']

    def scanner_context(self):
        if not self.has_scanner_context():
            return None
        self.__load_context()
        return self._json.get('scannerContext', None)

    def error_details(self):
        self.__load_context()
        return (self._json.get('errorMessage', None), self._json.get('errorStacktrace', None))

    def error_message(self):
        self.__load_context()
        return self._json.get('errorMessage', None)

    def audit(self, audit_settings):
        if not audit_settings['audit.projects.exclusions']:
            util.logger.info('Project exclusions auditing disabled, skipping...')
            return []
        if not self.has_scanner_context():
            util.logger.info("Last background task of project key '%s' has no scanner context, can't audit exclusions",
                             self.component())
            return []
        problems = []
        context = self.scanner_context().split("\n  - ")
        for line in context:
            if not line.startswith('sonar'):
                continue
            (prop, val) = line.split("=", 2)
            if prop not in ('sonar.exclusions', 'sonar.global.exclusions'):
                continue
            for excl in [x.strip() for x in val.split(',')]:
                for susp in SUSPICIOUS_EXCLUSIONS:
                    if not re.search(susp, excl):
                        continue
                    rule = rules.get_rule(rules.RuleId.PROJ_SUSPICIOUS_EXCLUSION)
                    msg = rule.msg.format(f"project key '{self.component()}'", excl)
                    problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        return problems


def search(only_current=False, component_key=None, endpoint=None):
    params={'status': ','.join(STATUSES)}
    if only_current:
        params['onlyCurrents'] = 'true'
    if component_key is not None:
        params['component'] = component_key
    resp = env.get('ce/activity', params=params, ctxt=endpoint)
    data = json.loads(resp.text)
    task_list = []
    for t in data['tasks']:
        task_list.append(Task(t['id'], endpoint, data=t))
    return task_list

def search_all_last(component_key=None, endpoint=None):
    return search(only_current=True, component_key=component_key, endpoint=endpoint)


def search_last(component_key, endpoint=None):
    return search(only_current=True, component_key=component_key, endpoint=endpoint)[0]


def search_all(component_key, endpoint=None):
    return search(component_key=component_key, endpoint=endpoint)

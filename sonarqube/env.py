#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "platform" concept

'''
import sys
import re
import datetime
import json
import requests
import sonarqube.utilities as util
import sonarqube.audit_problem as pb

HTTP_ERROR_MSG = "%s%s raised error %d: %s"
DEFAULT_URL = 'http://localhost:9000'

GLOBAL_PERMISSIONS = {
    "admin": "Global Administration",
    "gateadmin": "Administer Quality Gates",
    "profileadmin": "Administer Quality Profiles",
    "provisioning": "Create Projects",
    "portfoliocreator": "Create Portfolios",
    "applicationcreator": "Create Applications",
    "scan": "Run Analysis"
}

class Environment:

    def __init__(self, url, token):
        self.root_url = url
        self.token = token
        self.version = None
        self.major = None
        self.minor = None
        self.patch = None
        self.build = None

    def __str__(self):
        redacted_token = re.sub(r'(...).*(...)', r'\1***\2', self.token)
        return "{0}@{1}".format(redacted_token, self.root_url)

    def set_env(self, url, token):
        self.root_url = url
        self.token = token
        util.logger.debug('Setting environment: %s', str(self))

    def set_token(self, token):
        self.token = token

    def get_token(self):
        return self.token

    def get_credentials(self):
        return (self.token, '')

    def set_url(self, url):
        self.root_url = url

    def get_url(self):
        return self.root_url

    def get_version(self):
        if self.version is None:
            resp = self.get('/api/server/version')
            (self.major, self.minor, self.patch, self.build) = resp.text.split('.')
        return (int(self.major), int(self.minor), int(self.patch))

    def get_sysinfo(self):
        resp = self.get('system/info')
        sysinfo = json.loads(resp.text)
        return sysinfo

    def get(self, api, params = None):
        api = __normalize_api__(api)
        util.logger.debug('GET: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.get(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.get(url=self.root_url + api, auth=self.get_credentials(), params=params)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise
        if (r.status_code // 100) != 2:
            util.logger.error(HTTP_ERROR_MSG, self.root_url, api, r.status_code, r.text)
        return r

    def post(self, api, params = None):
        api = __normalize_api__(api)
        util.logger.debug('POST: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.post(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.post(url=self.root_url + api, auth=self.get_credentials(), params=params)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise
        if (r.status_code // 100) != 2:
            util.logger.error(HTTP_ERROR_MSG, self.root_url, api, r.status_code, r.text)
        return r

    def delete(self, api, params = None):
        api = __normalize_api__(api)
        util.logger.debug('DELETE: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.delete(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.delete(url=self.root_url + api, auth=self.get_credentials(), params=params)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise
        if (r.status_code // 100) != 2:
            util.logger.error(HTTP_ERROR_MSG, self.root_url, api, r.status_code, r.text)
        return r

    def urlstring(self, api, params):
        first = True
        url = "{0}{1}".format(str(self), api)
        if params is not None:
            for p in params:
                sep = '?' if first else '&'
                first = False
                if isinstance(params[p], datetime.date):
                    params[p] = util.format_date(params[p])
                url += '{0}{1}={2}'.format(sep, p, params[p])
        return url

    def __audit_project_default_visibility__(self):
        util.logger.info('Auditing project default visibility')
        problems = []
        resp = self.get('navigation/organization', params={'organization':'default-organization'})
        data = json.loads(resp.text)
        visi = data['organization']['projectVisibility']
        util.logger.info('Project default visibility is %s', visi)
        if visi != 'private':
            problems.append(
                pb.Problem(pb.Type.SECURITY, pb.Severity.HIGH,
                    'Project default visibility is {}, which can be a security risk'.format(visi)))
        return problems

    def __audit_admin_password__(self):
        util.logger.info('Auditing admin password')
        problems = []
        try:
            r = requests.get(url=self.root_url + '/api/authentication/validate', auth=('admin','admin'))
            data = json.loads(r.text)
            if data.get('valid', False):
                problems.append(
                    pb.Problem(pb.Type.SECURITY, pb.Severity.CRITICAL,
                        "User 'admin' still using the default password, this must be changed ASAP"))
            else:
                util.logger.info("User 'admin' default password has been changed")
        except requests.RequestException as e:
            util.logger.error("HTTP request exception for %s/%s: %s", self.root_url,
                              'api/authentication/validate', str(e))
            raise
        return problems

    def __get_permissions__(self, perm_type):
        resp = self.get('permissions/{0}'.format(perm_type), params={'ps': 100})
        data = json.loads(resp.text)
        active_perms = []
        for item in data.get(perm_type, []):
            if item['permissions']:
                active_perms.append(item)
        return active_perms

    def __audit_group_permissions__(self):
        util.logger.info('Auditing group global permissions')
        problems = []
        groups = self.__get_permissions__('groups')
        if len(groups) > 10:
            problems.append(
                pb.Problem(pb.Type.BAD_PRACTICE, pb.Severity.MEDIUM,
                           'Too many ({0}) groups with global permissions'.format(len(groups))))
        for gr in groups:
            if gr['name'] == 'Anyone':
                problems.append(pb.Problem(pb.Type.SECURITY, pb.Severity.HIGH,
                                         "Group 'Anyone' should not have any global permission"))
            if gr['name'] == 'sonar-users' and (
                    'admin' in gr['permissions'] or 'gateadmin' in gr['permissions'] or
                    'profileadmin' in gr['permissions'] or 'provisioning' in gr['permissions']):
                problems.append(
                    pb.Problem(pb.Type.GOVERNANCE, pb.Severity.MEDIUM,
                        "Group 'sonar-users' should not have admin, admin QG, admin QP or create project permissions"))

        perm_counts = __get_permissions_count__(groups)
        maxis = {'admin': 2, 'gateadmin': 2, 'profileadmin': 2, 'scan': 2, 'provisioning': 3}
        for perm in GLOBAL_PERMISSIONS:
            if perm in maxis and perm_counts[perm] > maxis[perm]:
                problems.append(
                    pb.Problem(pb.Type.BAD_PRACTICE, pb.Severity.MEDIUM,
                               'Too many ({}) groups with permission {}, {} max recommended'.format(
                                   perm_counts[perm], GLOBAL_PERMISSIONS[perm], maxis[perm])))
        return problems

    def __audit_user_permissions__(self):
        util.logger.info('Auditing users global permissions')
        problems = []
        users = self.__get_permissions__('users')
        if len(users) > 10:
            problems.append(
                pb.Problem(pb.Type.BAD_PRACTICE, pb.Severity.MEDIUM,
                    'Too many ({}) users with direct global permissions, use groups instead'.format(len(users))))

        perm_counts = __get_permissions_count__(users)
        maxis = {'admin': 3, 'gateadmin': 3, 'profileadmin': 3, 'scan': 3, 'provisioning': 3}
        for perm in GLOBAL_PERMISSIONS:
            if perm in maxis and perm_counts[perm] > maxis[perm]:
                problems.append(
                    pb.Problem(pb.Type.BAD_PRACTICE, pb.Severity.MEDIUM,
                        'Too many ({}) users with permission {}, use groups instead'.format(
                            perm_counts[perm], GLOBAL_PERMISSIONS[perm])))
        return problems

    def __audit_global_permissions__(self):
        util.logger.info('Auditing global permissions')
        return self.__audit_user_permissions__() + self.__audit_group_permissions__()

    def audit(self):
        util.logger.info('Auditing global settings')
        problems = []
        resp = self.get('settings/values')
        json_s = json.loads(resp.text)
        settings = {}
        for s in json_s['settings']:
            if 'value' in s:
                settings[s['key']] = s['value']
            else:
                settings[s['key']] = ','.join(s['values'])
        problems = __check_setting_value__(settings, 'sonar.forceAuthentication', 'true')
        problems += __check_setting_value__(settings, 'sonar.cpd.cross_project', 'false')
        problems += __check_setting_value__(settings, 'sonar.global.exclusions', '')
        if self.get_version() < (8,0,0):
            problems += __audit_setting_range__(settings, \
                'sonar.dbcleaner.daysBeforeDeletingInactiveShortLivingBranches', 10, 60, pb.Severity.MEDIUM)
        problems += __audit_setting_range__(settings, \
            'sonar.dbcleaner.daysBeforeDeletingClosedIssues', 10, 60, pb.Severity.MEDIUM)
        problems += __audit_setting_range__(settings, \
            'sonar.dbcleaner.hoursBeforeKeepingOnlyOneSnapshotByDay', 12, 240, pb.Severity.MEDIUM)
        problems += __audit_setting_range__(settings, \
            'sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByWeek', 2, 12,pb.Severity.MEDIUM)
        problems += __audit_setting_range__(settings, \
            'sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByMonth', 26, 104, pb.Severity.MEDIUM)
        problems += __audit_setting_range__(settings, \
            'sonar.dbcleaner.weeksBeforeDeletingAllSnapshots', 104, 260, pb.Severity.MEDIUM)
        problems += __audit_setting_defined__(settings, 'sonar.core.serverBaseURL', pb.Severity.HIGH)

        problems += __audit_maintainability_rating_grid__(settings['sonar.technicalDebt.ratingGrid'], pb.Severity.MEDIUM)
        problems += __audit_setting_range__(settings, 'sonar.technicalDebt.developmentCost', 20, 30, pb.Severity.MEDIUM)

        problems += self.__audit_project_default_visibility__()
        problems += audit_sysinfo(self.get_sysinfo())
        problems += self.__audit_admin_password__()
        problems += self.__audit_global_permissions__()
        return problems

#--------------------- Static methods, not recommended -----------------
# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.context = Environment("http://localhost:9000", '')

def set_env(url, token):
    this.context = Environment(url, token)
    util.logger.debug('Setting GLOBAL environment: %s@%s', token, url)

def set_token(token):
    this.context.set_token(token)

def get_token():
    return this.context.token

def get_credentials():
    return (this.context.token, '')

def set_url(url):
    this.context.set_url(url)

def get_url():
    return this.context.root_url

def __normalize_api__(api):
    api = api.lower()
    if re.match(r'/api', api):
        pass
    elif re.match(r'api', api):
        api = '/' + api
    elif re.match(r'/', api):
        api = '/api' + api
    else:
        api = '/api/' + api
    return api

def get(api, params = None, ctxt = None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.get(api, params)

def post(api, params = None, ctxt = None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.post(api, params)

def delete(api, params = None, ctxt = None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.delete(api, params)

def __get_memory__(setting):
    for s in setting.split(' '):
        if re.match('-Xmx', s):
            val = int(s[4:-1])
            unit = s[-1].upper()
            if unit == 'M':
                return val
            elif unit == 'G':
                return val * 1024
            elif unit == 'K':
                return val // 1024
    return None

def __get_store_size__(setting):
    (val, unit) = setting.split(' ')
    if unit == 'MB':
        return int(val)
    elif unit == 'GB':
        return int(val) * 1024
    return None

def __audit_setting_range__(settings, key, min_val, max_val, severity):
    value = int(settings[key])
    problems = []
    if value >= min_val and value <= max_val:
        util.logger.info("Setting %s value %d is within recommended range [%d-%d]",
                         key, value, min_val, max_val)
    else:
        problems.append(
            pb.Problem(pb.Type.CONFIGURATION, severity,
                "Setting {} value {} is outside recommended range [{}-{}]".format(
                    key, value, min_val, max_val)))
    return problems

def __check_setting_value__(settings, key, value):
    s = settings.get(key, '')
    if s == value:
        util.logger.info("Setting %s has common/recommended value '%s'", key, s)
    else:
        util.logger.warning("Setting %s has potentially incorrect/unsafe value '%s'", key, s)
        return 1
    return 0

def __audit_setting_defined__(settings, key, severity):
    problems = []
    if key in settings and settings[key] != '':
        util.logger.info("Setting %s is set with value %s", key, settings[key])
    else:
        problems.append(
            pb.Problem(pb.Type.CONFIGURATION, severity,
                       "Setting {} is not set, although it should".format(key)))
    return problems

def __audit_maintainability_rating_range__(value, min_val, max_val, rating_letter):
    value = float(value)
    problems = []
    util.logger.info('Checking that maintainability rating threshold %3.0f%% for %s is \
within recommended range [%3.0f%%-%3.0f%%]', value*100, rating_letter, min_val*100, max_val*100)
    if value < min_val or value > max_val:
        problems.append(pb.Problem(pb.Type.CONFIGURATION, pb.Severity.MEDIUM,
            'Maintainability rating threshold {}% for {} is \
NOT within recommended range [{}%-{}%]'.format(value*100, rating_letter, min_val*100, max_val*100)))
    return problems

def __audit_maintainability_rating_grid__(grid):
    (a, b, c, d) = grid.split(',')
    issues = __audit_maintainability_rating_range__(a, 0.03, 0.05, 'A')
    issues += __audit_maintainability_rating_range__(b, 0.07, 0.10, 'B')
    issues += __audit_maintainability_rating_range__(c, 0.15, 0.20, 'C')
    issues += __audit_maintainability_rating_range__(d, 0.40, 0.50, 'D')
    return issues

def __check_log_level__(sysinfo):
    util.logger.info('Auditing log levels')
    problems = []
    log_level = sysinfo["Web Logging"]["Logs Level"]
    if log_level == "DEBUG":
        problems.append(
            pb.Problem(pb.Type.PERFORMANCE, pb.Severity.HIGH,
                "Log level is set to DEBUG, this may affect platform performance, \
reverting to INFO is recommended")
        )
    elif log_level == "TRACE":
        problems.append(
            pb.Problem(pb.Type.PERFORMANCE, pb.Severity.CRITICAL,
                "Log level set to TRACE, this does very negatively affect platform performance, \
reverting to INFO is required")
        )
    return problems

def __check_web_settings__(sysinfo):
    util.logger.info('Auditing Web settings')
    problems = []
    web_ram = __get_memory__(sysinfo['Settings']['sonar.web.javaOpts'])
    if web_ram < 1024 or web_ram > 2048:
        problems.append(
            pb.Problem(pb.Type.PERFORMANCE, pb.Severity.HIGH,
                "sonar.web.javaOpts -Xmx memory setting value is {} MB, \
not in recommended range [1024-2048]".format(web_ram))
        )
    else:
        util.logger.info("sonar.web.javaOpts -Xmx memory setting value is %d MB, \
within the recommended range [1024-2048]", web_ram)
    return problems

def __audit_ce_settings__(sysinfo):
    util.logger.info('Auditing CE settings')
    problems = []
    ce_ram = __get_memory__(sysinfo['Settings']['sonar.ce.javaOpts'])
    ce_tasks = sysinfo['Compute Engine Tasks']
    ce_workers = ce_tasks['Worker Count']
    if ce_workers > 4:
        problems.append(
            pb.Problem(pb.Type.PERFORMANCE, pb.Type.HIGH,
                "{} CE workers configured, more than the max 4 recommended".format(ce_workers))
        )
    else:
        util.logger.info("%d CE workers configured, correct compared to the max 4 recommended", ce_workers)

    if ce_ram < 512 * ce_workers or ce_ram > 2048 * ce_workers:
        problems.append(
            pb.Problem(pb.Type.PERFORMANCE, pb.Severity.HIGH,
                "sonar.ce.javaOpts -Xmx memory setting value is {} MB, \
not in recommended range ([512-2048] x {} workers)".format(ce_ram, ce_workers))
        )
    else:
        util.logger.info("sonar.ce.javaOpts -Xmx memory setting value is %d MB, \
within recommended range ([512-2048] x %d workers)", ce_ram, ce_workers)
    return problems

def __check_ce_background_tasks__(sysinfo):
    util.logger.info('Auditing CE background tasks')
    problems =[]
    ce_tasks = sysinfo['Compute Engine Tasks']
    ce_workers = ce_tasks['Worker Count']
    ce_success = ce_tasks["Processed With Success"]
    ce_error = ce_tasks["Processed With Error"]
    ce_pending = ce_tasks["Pending"]
    failure_rate = ce_error / (ce_success+ce_error)
    if ce_error > 10 and failure_rate > 0.01:
        problems.append(
            pb.Problem(pb.Type.OPERATIONS, pb.Severity.HIGH,
                'Background task failure rate ({}%) is high, \
verify failed background tasks'.format(int(failure_rate*100)))

        )
    else:
        util.logger.info('Number of failed background tasks (%d), and failure rate %d%% is OK',
                         ce_error, failure_rate)

    if ce_pending > 100:
        problems.append(
            pb.Problem(pb.Type.PERFORMANCE, pb.Severity.CRITICAL,
                'Number of pending background tasks ({}) is very high, verify CE dimensioning'.format(
                    ce_pending))
        )
    elif ce_pending > 20 and ce_pending > (10*ce_workers):
        pb.Problem(pb.Type.PERFORMANCE, pb.Severity.HIGH,
                'Number of pending background tasks ({}) is  high, verify CE dimensioning'.format(
                    ce_pending))
    else:
        util.logger.info('Number of pending background tasks (%d) is OK', ce_pending)
    return problems

def __audit_es_settings__(sysinfo):
    util.logger.info('Auditing Search Server settings')
    problems = []
    es_ram = __get_memory__(sysinfo['Settings']['sonar.search.javaOpts'])
    index_size = __get_store_size__(sysinfo['Search State']['Store Size'])
    if es_ram < 2 * index_size and es_ram < index_size + 1000:
        problems.append(
            pb.Problem(pb.Type.PERFORMANCE, pb.Severity.CRITICAL,
                "sonar.search.javaOpts -Xmx memory setting value is {} MB,\
too low for index size of {} MB".format(es_ram, index_size))
        )
    else:
        util.logger.info("Search server memory %d MB is correct wrt to index size of %d MB", es_ram, index_size)
    return problems

def __audit_dce_settings__(sysinfo):
    util.logger.util('Auditing DCE settings')
    problems = []
    stats = sysinfo.get('Statistics')
    if stats is None:
        util.logger.error("Can't verify edition in System Info File, was it corrupted or redacted ?")
        return problems
    edition = stats.get('edition', None)
    if stats is None:
        util.logger.error("Can't verify edition in System Info File, was it corrupted or redacted ?")
        return problems
    if edition != "datacenter":
        util.logger.info('Not a Data Center Edition, skipping DCE checks')
        return problems
    # Verify that app nodes have the same plugins installed
    appnodes = sysinfo['Application Nodes']
    ref_plugins = json.dumps(appnodes[0]['Plugins'], sort_keys=True, indent=3, separators=(',', ': '))
    ref_name = appnodes[0]['Name']
    ref_version = appnodes[0]['System']['Version']
    for node in appnodes:
        node_version = node['System']['Version']
        if node_version != ref_version:
            problems.append(
                pb.Problem(pb.Type.OPERATIONS, pb.Severity.CRITICAL,
                    'App nodes {} and {} do not run the same SonarQube versions, this must be corrected ASAP'.format(
                        ref_name, node['Name']))
            )
        node_plugins = json.dumps(node['Plugins'], sort_keys=True, indent=3, separators=(',', ': '))
        if node_plugins != ref_plugins:
            problems.append(
                pb.Problem(pb.Type.OPERATIONS, pb.Severity.CRITICAL,
                    'Some plugins on app nodes {} and {} are different, this must be corrected ASAP'.format(
                        ref_name, node['Name']))
            )
        if not node['System']['Official Distribution']:
            problems.append(
                pb.Problem(pb.Type.OPERATIONS, pb.Severity.CRITICAL,
                    'Node {} does not run an official distribution of SonarQube'.format(node['Name']))
            )
        if node['Health'] != "GREEN":
            problems.append(
                pb.Problem(pb.Type.OPERATIONS, pb.Severity.HIGH,
                    'Node {} health is {}, it should be GREEN'.format(node['Name'], node['Health']))
            )
    return problems

def audit_sysinfo(sysinfo):
    issues = 0
    issues += __check_web_settings__(sysinfo)
    issues += __audit_ce_settings__(sysinfo)
    issues += __check_ce_background_tasks__(sysinfo)
    issues += __audit_es_settings__(sysinfo)
    issues += __audit_dce_settings__(sysinfo)
    return issues


def __get_permissions_count__(users_or_groups):
    perm_counts = dict(zip(GLOBAL_PERMISSIONS.keys(), [0, 0, 0, 0, 0, 0, 0]))
    for user_or_group in users_or_groups:
        for perm in GLOBAL_PERMISSIONS:
            if perm in user_or_group['permissions']:
                perm_counts[perm] += 1
    return perm_counts

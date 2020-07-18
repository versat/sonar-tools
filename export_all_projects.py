#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3
import os
import re
import json
import argparse
import requests
import sonarqube.measures as measures
import sonarqube.metrics as metrics
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env

parser = util.set_common_args('Extract measures of projects')
parser.add_argument('-p', '--pollInterval', required=False, help='Interval to check exports status')

args = parser.parse_args()
myenv = env.Environment(url=args.url, token=args.token)
kwargs = vars(args)
util.check_environment(kwargs)
poll_interval = 1
if args.pollInterval is not None:
    poll_interval = int(args.pollInterval)

project_list = projects.get_projects(False, myenv)
nb_projects = len(project_list)
util.logger.info("%d projects to export", nb_projects)
i = 0
for p in project_list:
    key = p['key']
    dump_file = projects.Project(key, sqenv = myenv).export(poll_interval)
    if dump_file is not False:
        print("{0},{1}".format(key, os.path.basename(dump_file)))
    i += 1
    if (i % 5) == 0:
        util.logger.info("%d/%d projects exported: %d%%", i, nb_projects, int(i * 100/nb_projects))

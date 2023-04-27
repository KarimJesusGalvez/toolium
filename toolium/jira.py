# -*- coding: utf-8 -*-
"""
Copyright 2015 Telefónica Investigación y Desarrollo, S.A.U.
This file is part of Toolium.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import logging
import os
import re
from os import path
from jira import JIRA, Issue
from jira.exceptions import JIRAError
from toolium.config_driver import get_error_message_from_exception
from toolium.driver_wrappers_pool import DriverWrappersPool

logger = logging.getLogger(__name__)


class JiraServer:

    def __init__(self, execution_url, token=None):
        global logger

        logger = logging.getLogger("Jira.Server")
        self.url = execution_url
        self._token = token
        self.server: JIRA = None

    def __enter__(self):
        server_url = self.url
        headers = JIRA.DEFAULT_OPTIONS["headers"]
        headers["Authorization"] = f"Bearer {self._token}"
        logger.info("Starting Jira server...")
        self.server = JIRA(server=server_url, options={"headers": headers, 'verify': True}, get_server_info=True)
        return self.server

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.server.close()
        logger.info("Jira server closed//")


# Dict to save tuples with jira keys, their test status, comments and attachments
jira_tests_status = {}

# List to save temporary test attachments
attachments = []

# Jira configuration
enabled = None
jiratoken = None
project_id = 0
project_key = ""
project_name = ""
execution_url = ''
summary_prefix = None
labels = None
comments = None
fix_version = None
build = None
only_if_changes = None


def jira(test_key):
    """Decorator to update test status in Jira

    :param test_key: test case key in Jira
    :returns: jira test
    """

    def decorator(test_item):
        def modified_test(*args, **kwargs):
            save_jira_conf()
            try:
                test_item(*args, **kwargs)
            except Exception as e:
                error_message = get_error_message_from_exception(e)
                test_comment = "The test '{}' has failed: {}".format(args[0].get_method_name(), error_message)
                add_jira_status(test_key, 'Fail', test_comment)
                raise
            add_jira_status(test_key, 'Pass', None)

        modified_test.__name__ = test_item.__name__
        return modified_test

    return decorator


def save_jira_conf():
    """Read Jira configuration from properties file and save it"""
    global enabled, jiratoken, project_id, project_key, project_name, execution_url, summary_prefix, labels, comments,\
        fix_version, build, only_if_changes, attachments
    config = DriverWrappersPool.get_default_wrapper().config
    enabled = config.getboolean_optional('Jira', 'enabled')
    jiratoken = config.get_optional('Jira', 'token')
    project_id = int(config.get_optional('Jira', 'project_id'))
    project_key = int(config.get_optional('Jira', 'project_key'))
    project_name = int(config.get_optional('Jira', 'project_name'))
    execution_url = config.get_optional('Jira', 'execution_url')
    summary_prefix = config.get_optional('Jira', 'summary_prefix')
    labels_raw = config.get_optional('Jira', 'labels')
    labels_raw = labels_raw.replace("[", "").replace("]", "")
    labels = []
    for label in labels_raw.split(","):
        labels.append(label)
    comments = config.get_optional('Jira', 'comments')
    fix_version = config.get_optional('Jira', 'fixversion')
    build = config.get_optional('Jira', 'build')
    only_if_changes = config.getboolean_optional('Jira', 'onlyifchanges')
    attachments = []
    jira_properties = {"enabled": enabled, "execution_url": execution_url, "summary_prefix": summary_prefix,
                       "labels": labels, "comments": comments, "fix_version": fix_version, "build": build,
                       "only_if_changes": only_if_changes, "attachments": attachments}
    logger.debug("Jira properties read:" + jira_properties.__str__())


def add_attachment(attachment):
    """ Add a file path to attachments list

    :param attachment: attachment file path
    """
    if attachment:
        attachments.append(attachment)
        logger.info("Attachement added from: " + attachment)


def add_jira_status(test_key, test_status, test_comment):
    """Save test status and comments to update Jira later

    :param test_key: test case key in Jira
    :param test_status: test case status
    :param test_comment: test case comments
    """
    global attachments
    if test_key and enabled:
        if test_key in jira_tests_status:
            # Merge data with previous test status
            previous_status = jira_tests_status[test_key]
            logger.debug("Found previous data for " + test_key.__str__())

            test_status = 'Pass' if previous_status[1] == 'Pass' and test_status == 'Pass' else 'Fail'
            if previous_status[2] and test_comment:
                test_comment = '{}\n{}'.format(previous_status[2], test_comment)
            elif previous_status[2] and not test_comment:
                test_comment = previous_status[2]
            attachments += previous_status[3]
        # Add or update test status
        jira_tests_status[test_key] = (test_key, test_status, test_comment, attachments)
    elif enabled and not test_key:
        logger.error("Status not updated, invalid test key")


def change_all_jira_status():
    """Iterate over all jira test cases, update their status in Jira and clear the dictionary"""
    for test_status in jira_tests_status.values():
        change_jira_status(*test_status)
    jira_tests_status.clear()
    if enabled:
        logger.debug("Update attempt complete, clearing queue")
    else:
        logger.debug("Jira disabled, upload skipped")


def check_jira_args(server: JIRA):
    global project_name, project_key, project_id

    available_keys = []
    for project_instance in server.projects():
        # TODO turn into dict
        available_keys.append([project_instance.raw['name'], project_instance.raw['key'],project_instance.raw['id']])

    if project_id:
        project_option = project_id
    elif project_key:
        project_option = project_key
    else:
        project_option = project_name

    # TODO create def
    if project_option not in available_keys:
        msg = f"No existe el proyecto '{project_option}'"
        logger.warning(f"Available projects for your user: '{available_keys}'")
        logger.error(msg)
        raise ValueError(msg)

    # TODO create def
    # TODO Refactor duplicate ifs
    if project_id:
        project_key = server.project(str(project_id)).raw["key"]
    elif project_key:
        project_id = int(server.project(project_key).raw["id"])
    else:
        for version in available_keys:
            if project_name in version:
                project_key = version[1]
                project_id = int(version[2])

    # TODO create def
    available_fixversions = []
    for version in server.project_versions(project_name):
        available_fixversions.append(version.raw["name"])
    if fix_version not in available_fixversions:
        msg = f"No existe la fix version '{fix_version}'"
        logger.warning(f"Available fixversions for project {server.project(project_name)} are {available_fixversions}")
        logger.error(msg)
        raise ValueError(msg)


def change_jira_status(test_key, test_status, test_comment, test_attachments: list[str]):
    """Update test status in Jira

    :param test_key: test case key in Jira
    :param test_status: test case status
    :param test_comment: test case comments
    :param test_attachments: list of absolutes paths of test case attachment files
    """

    if not execution_url:
        logger.warning("Test Case '%s' can not be updated: execution_url is not configured", test_key)
        return

    logger.info("Updating Test Case '%s' in Jira with status %s", test_key, test_status)
    composed_comments = comments
    if test_comment:
        composed_comments = '{}\n{}'.format(comments, test_comment) if comments else test_comment
    payload = {'jiraTestCaseId': test_key, 'jiraStatus': test_status, 'summaryPrefix': summary_prefix,
               'labels': labels, 'comments': composed_comments, 'version': fix_version, 'build': build}
    if only_if_changes:
        payload['onlyIfStatusChanges'] = 'true'
    try:
        with JiraServer(execution_url, jiratoken) as server:

            check_jira_args(server)
            existing_issues = execute_query(server, 'issue = ' + test_key)
            if not existing_issues:
                logger.warning("Jira Issue not found,...")
                return
                # TODO issue = new_testcase(server, project_id, summary=scenarioname, description=description)
                # test_key = issue.key

            logger.debug("Creating execution for " + test_key)
            new_execution = create_test_execution(server, test_key, project_id,
                                                  summary_prefix, existing_issues[0].fields.summary, fix_version,
                                                  existing_issues[0].fields.labels, labels)
            logger.info(f"Created execution {new_execution.key} for test " + test_key)

            # TODO massage payload, labels??
            logger.debug("Update skipped for " + test_key)
            # issue.update(fields=payload, jira=server)

            # TODO wait to create test execution before transitioning to behave status
            logger.debug("Transitioning " + new_execution.key)
            transition(server, new_execution, test_status)

            add_results(server, new_execution.key, test_attachments)

    except JIRAError as e:
        print_trace(logger, e)
        logger.error("Exception while updating Issue '%s': %s", test_key, e)
        return


def execute_query(jira: JIRA, query: str):
    logger = logging.getLogger("Jira.Queries")

    logger.info(f"executing query: {query} ...\n")
    existing_issues = jira.search_issues(query)

    issuesfound = ""
    for issue in existing_issues:
        issuesfound += f'\n{issue} {jira.issue(issue).fields.summary}'
    if issuesfound:
        logger.info("Found issue/s:" + issuesfound)
    return existing_issues


def create_test_execution(server: JIRA, issueid: str, projectid: int, summary_prefix: str, test_summary: str,
                          fix_version: str, parent_labels: list, new_labels: list = None, description: str = " ") -> Issue:
    """Creates an execution linked to the TestCase provided"""
    issue_dict = {
        'project': {'id': projectid},
        'assignee': {'name': server.current_user()},
        'issuetype': {'name': 'Test Case Execution'},
        'parent': {'key': issueid},
        'summary': str(summary_prefix) + " Execution of " + test_summary + " " + issueid,
        'fixVersions': [{'name': fix_version}],
        # TODO set priority as config input?
        # 'priority': {'name': 'Minor', "id": 10101},
        'labels': parent_labels + new_labels,
        # 'versions': [{'name': fix_version}],
        'description': description,
    }

    return server.create_issue(fields=issue_dict)


def transition(server: JIRA, issue: Issue, test_status: str):
    """
    Transitions the issue to a new state, see issue workflows in the project for available options
    param test_status: the new status of the issue
    """
    logger.info("Setting new status for " + issue.key + "from " + issue.fields.status.raw['name'] + " to " + test_status)
    try:
        server.transition_issue(issue.key, transition=test_status.lower())
    except JIRAError:
        # TODO Get available transitions
        logger.warning("Available transitions for %s are %s", issue.key, server.transitions(issue.key))
        logger.error("Error transitioning Test Case '%s' to status [%s]", issue.key, test_status)

        return
    logger.debug("Transitioned issue to status %s", test_status)


def add_results(jira: JIRA, issueid: str, attachements: list[str] = None):
    """Adds the results to the execution or the associated test case instead"""

    def addscreenshots(issueid: str, attachements: list[str] = None):
        """
            Attach the screenshots found the report folder to the jira issue provided
            param issueid: Full Jira ID
            param attachements: Absolute paths of attachments
            Raises FileNotFound: if an attachement file is not found
        """

        if attachements:
            for filepath in attachements:
                if os.path.isfile(path.join(filepath)):
                    with open(filepath, 'rb') as file:
                        logger.debug("Opened screenshot " + file.name)
                        jira.add_attachment(issue=issueid, attachment=file)
                        logger.info("Attached " + file.name + " into " + issueid)
        else:
            screenshotspath = path.join(path.dirname(__file__), ".", DriverWrappersPool.screenshots_directory)
            logger.debug("Reading screenshot folder " + screenshotspath)

            if len(os.listdir(screenshotspath)) < 1:
                logger.warning("Screenshot folder empty...")
                return

            for filename in os.listdir(screenshotspath):
                if os.path.isfile(path.join(screenshotspath, filename)):
                    with open(os.path.join(screenshotspath, filename), 'rb') as file:
                        logger.debug("Opened screenshot " + file.name)
                        jira.add_attachment(issue=issueid, attachment=file)
                        logger.info("Attached " + filename + " into " + issueid)
        logger.info("Screenshots uploaded...")

    def addlogs(issueid: str):
        """
            Attach the logs in the report folder to the jira issue provided
            param issueid Full Jira ID
            Raises FileNotFound Error if the log file is not found in reports
        """
        logpath = path.join(path.dirname(__file__),
                            ".", DriverWrappersPool.screenshots_directory, "..", "..", "toolium.log")

        with open(logpath, 'rb') as file:
            logger.debug("Opened log file " + file.name)
            jira.add_attachment(issue=issueid, attachment=file)
            logger.info("Attached log into " + issueid)

    try:
        logger.info("Adding results to issue...")
        addscreenshots(issueid, attachements) if attachements else addscreenshots(issueid)
        addlogs(issueid)
        logger.debug("Results added to issue " + issueid)

    except FileNotFoundError as error:
        # TODO catch jira exception types
        print_trace(logger, error)
        logger.error("Results not added, exception:" + str(error))


def get_error_message(response_content: str):
    """Extract error message from the HTTP response

    :param response_content: HTTP response from test case execution API
    :returns: error message
    """
    apache_regex = re.compile(r'.*<u>(.*)</u></p><p>.*')
    match = apache_regex.search(response_content)
    if match:
        error_message = match.group(1)
        logger.debug("Error message extracted from HTTP response with regex:" + apache_regex.__repr__())

    else:
        local_regex = re.compile(r'.*<title>(.*)</title>.*')
        match = local_regex.search(response_content)
        if match:
            error_message = match.group(1)
        else:
            error_message = response_content
        logger.debug("Error message extracted from HTTP response with regex:" + local_regex.__repr__())

    return error_message


def print_trace(logger, e):
    # TODO move to utils as stand alone
    # TODO set custom JiraError for toolium
    import traceback

    trace = traceback.format_tb(e.__traceback__, 30)
    final_stack = ''
    for count in range(len(trace)):
        final_stack += f'Trace stack {count} {trace[count]}'
    logger.error(f'Error Trace:\n{final_stack}')
    logger.error(f'Error: {e.__class__}')
    if hasattr(e, "msg"):
        logger.error(f'Error Message: {e.msg}')
    elif e.__class__ == "<class 'AttributeError'>":
        logger.error(f'Error Message: {e.obj} has no {e.name}')
    else:
        logger.error(e.args)

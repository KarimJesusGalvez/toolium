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
    global enabled, jiratoken, execution_url, summary_prefix, labels, comments,\
        fix_version, build, only_if_changes, attachments
    config = DriverWrappersPool.get_default_wrapper().config
    enabled = config.getboolean_optional('Jira', 'enabled')
    jiratoken = config.get_optional('Jira', 'token')
    execution_url = config.get_optional('Jira', 'execution_url')
    summary_prefix = config.get_optional('Jira', 'summary_prefix')
    labels = config.get_optional('Jira', 'labels')
    comments = config.get_optional('Jira', 'comments')
    fix_version = config.get_optional('Jira', 'fixversion')
    build = config.get_optional('Jira', 'build')
    only_if_changes = config.getboolean_optional('Jira', 'onlyifchanges')
    attachments = []
    jira_properties = {"enabled": enabled, "execution_url": execution_url, "summary_prefix": summary_prefix,
                       "labels": labels, "comments": comments, "fix_version": fix_version, "build": build,
                       "only_if_changes": only_if_changes, "attachments": attachments}
    logger.debug("Jira properties set:" + jira_properties.__str__())


def add_attachment(attachment):
    """ Add a file path to attachments list

    :param attachment: attachment file path
    """
    if attachment:
        attachments.append(attachment)
        logger.info("Attachement Added from: " + attachment)


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
    logger.debug("Update attampt complete, clearing queue")


def change_jira_status(test_key, test_status, test_comment, test_attachments):
    """Update test status in Jira

    :param test_key: test case key in Jira
    :param test_status: test case status
    :param test_comment: test case comments
    :param test_attachments: test case attachments
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
        if test_attachments and len(test_attachments) > 0:
            files = dict()
            for index in range(len(test_attachments)):
                files['attachments{}'.format(index)] = open(test_attachments[index], 'rb')
        else:
            files = None
        headers = {
            "host": execution_url.split("//")[1],
            "Cache-Control": "no-cache",
            # 'Accept': 'application/json;charset=UTF-8',  # default for REST
            "Content-Type": "application/json",  # ;charset=UTF-8',
            # 'Accept': 'application/json',  # default for REST
            # 'Pragma': 'no-cache',
            # 'Expires': 'Thu, 01 Jan 1970 00:00:00 GMT'
            "X-Atlassian-Token": "no-check",
        }
        payload = {'jiraTestCaseId': test_key, 'jiraStatus': test_status, 'summaryPrefix': summary_prefix,
                   'labels': labels, 'comments': composed_comments, 'version': fix_version, 'build': build}
        body = {"update":{
                          # "summary":[{"set":"Bug in business logic"}],
                          # "components":[{"set":""}],
                          # "timetracking":[{"edit":{"originalEstimate":"1w 1d","remainingEstimate":"4d"}}],
                          "labels":[labels]},
                "fields":{
                    # "summary":"This is a shorthand for a set operation on the summary field",

                    }
                }

        if jiratoken:
            headers["Authorization"] = f"Bearer {jiratoken}"
            logger.debug("Sending PUT request to " + execution_url + "/rest/api/2/issue/" + test_key +
                         " with payload" + json.dumps(payload))
            # TODO fix GET 401 Unauthorized after PUT 302 Redirect (Auth Header is misssing in subsequent GET)

            response = requests.put(execution_url + "/rest/api/2/issue/" + test_key,
                                    data=json.dumps(payload), files=files)
            logger.debug("Request sent, returned " + str(response.status_code))

        else:
            logger.debug("Jira OAuth token not found")
            logger.debug("Sending POST request to " + execution_url + test_key + " with payload" + payload.__str__())
            response = requests.post(execution_url, data=payload, files=files)

    except Exception as e:
        logger.warning("Error updating Test Case '%s': %s", test_key, e)
        return

    if response.status_code >= 400:
        logger.warning("Error updating Test Case '%s': [%s] %s", test_key, response.status_code,
                       get_error_message(response.content.decode()))
    else:
        logger.debug("Response with status " + str(response.status_code) +
                     " is: '%s'", response.content.decode().splitlines()[0])


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

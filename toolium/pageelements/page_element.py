# -*- coding: utf-8 -*-
u"""
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

from toolium.driver_wrapper import DriverWrappersPool
from toolium.visual_test import VisualTest


class PageElement(object):
    """Class to represent a web or a mobile page element

    Attributes:
        driver_wrapper: driver wrapper instance
        driver: webdriver instance
        config: driver configuration
        utils: test utils instance
        locator: tuple with locator type and locator value
        parent: element from which to find actual element

    :type driver_wrapper: toolium.driver_wrapper.DriverWrapper
    :type driver: selenium.webdriver.remote.webdriver.WebDriver or appium.webdriver.webdriver.WebDriver
    :type config: toolium.config_parser.ExtendedConfigParser
    :type utils: toolium.utils.Utils
    :type locator: (selenium.webdriver.common.by.By or appium.webdriver.common.mobileby.MobileBy, str)
    :type parent: selenium.webdriver.remote.webelement.WebElement or appium.webdriver.webelement.WebElement
                  or toolium.pageelements.PageElement
                  or (selenium.webdriver.common.by.By or appium.webdriver.common.mobileby.MobileBy, str)
    """
    driver_wrapper = None
    driver = None
    config = None
    utils = None
    locator = None
    parent = None
    _element = None

    def __init__(self, by, value, parent=None):
        """Initialize the PageElement object with the given locator components.

        If parent is not None, find_element will be performed over it, instead of
        using the driver's method, so it can find nested elements.

        :param by: locator type
        :param value: locator value
        :param parent: parent element (WebElement, PageElement or locator tuple)
        """
        self.locator = (by, value)
        self.parent = parent
        self.set_driver_wrapper()

    def set_driver_wrapper(self, driver_wrapper=None):
        """Initialize driver_wrapper, driver, config and utils

        :param driver_wrapper: driver wrapper instance
        """
        self.driver_wrapper = driver_wrapper if driver_wrapper else DriverWrappersPool.get_default_wrapper()
        # Add some driver_wrapper attributes to page element instance
        self.driver = self.driver_wrapper.driver
        self.config = self.driver_wrapper.config
        self.utils = self.driver_wrapper.utils

    @property
    def element(self):
        """Find WebElement using element locator

        :returns: web element object
        :rtype: selenium.webdriver.remote.webelement.WebElement or appium.webdriver.webelement.WebElement
        """
        if not self._element:
            if self.parent:
                self._element = self.utils.get_element(self.parent).find_element(*self.locator)
            else:
                self._element = self.driver.find_element(*self.locator)
        return self._element

    def scroll_element_into_view(self):
        """Scroll element into view

        :returns: page element instance
        """
        y = self.element.location['y']
        self.driver.execute_script('window.scrollTo(0, {0})'.format(y))
        return self

    def wait_until_visible(self, timeout=10):
        """Search element and wait until it is visible

        :param timeout: max time to wait
        :returns: page element instance
        """
        self._element = self.utils.wait_until_element_visible(self.locator, timeout)
        return self

    def wait_until_not_visible(self, timeout=10):
        """Search element and wait until it is not visible

        :param timeout: max time to wait
        :returns: page element instance
        """
        self._element = self.utils.wait_until_element_not_visible(self.locator, timeout)
        return self

    def assert_screenshot(self, filename, threshold=0, exclude_elements=[]):
        """Assert that a screenshot of the element is the same as a screenshot on disk, within a given threshold.

        :param filename: the filename for the screenshot, which will be appended with ``.png``
        :param threshold: the threshold for triggering a test failure
        :param exclude_elements: list of WebElements, PageElements or element locators as a tuple (locator_type,
                                 locator_value) that must be excluded from the assertion
        """
        VisualTest(self.driver_wrapper).assert_screenshot(self.element, filename, self.__class__.__name__, threshold,
                                                          exclude_elements)

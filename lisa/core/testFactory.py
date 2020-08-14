from typing import Callable, Dict, List, Optional, Type

from singleton_decorator import singleton  # type: ignore

from lisa.core.testSuite import TestSuite
from lisa.util.exceptions import LisaException
from lisa.util.logger import get_logger


class TestCaseData:
    def __init__(
        self,
        method: Callable[[], None],
        description: str,
        priority: Optional[int] = 2,
        name: str = "",
    ):
        if name is not None and name != "":
            self.name = name
        else:
            self.name = method.__name__
        self.full_name = method.__qualname__.lower()
        self.method = method
        self.description = description
        self.priority = priority
        self.suite: TestSuiteData

        self.key: str = self.name.lower()


class TestSuiteData:
    def __init__(
        self,
        test_class: Type[TestSuite],
        area: Optional[str],
        category: Optional[str],
        description: str,
        tags: List[str],
        name: str = "",
    ):
        self.test_class = test_class
        if name is not None and name != "":
            self.name: str = name
        else:
            self.name = test_class.__name__
        self.key = self.name.lower()
        self.area = area
        self.category = category
        self.description = description
        self.tags = tags
        self.cases: Dict[str, TestCaseData] = dict()

    def add_case(self, test_case: TestCaseData) -> None:
        if self.cases.get(test_case.key) is None:
            self.cases[test_case.key] = test_case
        else:
            raise LisaException(
                f"TestSuiteData has test method {test_case.key} already"
            )


@singleton
class TestFactory:
    def __init__(self) -> None:
        self.suites: Dict[str, TestSuiteData] = dict()
        self.cases: Dict[str, TestCaseData] = dict()

        self._log = get_logger("init", "test")

    def add_class(
        self,
        test_class: Type[TestSuite],
        area: Optional[str],
        category: Optional[str],
        description: str,
        tags: List[str],
        name: Optional[str],
    ) -> None:
        if name is not None:
            name = name
        else:
            name = test_class.__name__
        key = name.lower()
        test_suite = self.suites.get(key)
        if test_suite is None:
            test_suite = TestSuiteData(test_class, area, category, description, tags)
            self.suites[key] = test_suite
        else:
            raise LisaException(f"TestFactory duplicate test class name: {key}")

        class_prefix = f"{key}."
        for test_case in self.cases.values():
            if test_case.full_name.startswith(class_prefix):
                self._add_case_to_suite(test_suite, test_case)
        self._log.info(
            f"registered test suite '{test_suite.key}' "
            f"with test cases: '{', '.join([key for key in test_suite.cases])}'"
        )

    def add_method(
        self, test_method: Callable[[], None], description: str, priority: Optional[int]
    ) -> None:
        test_case = TestCaseData(test_method, description, priority)
        full_name = test_case.full_name

        if self.cases.get(full_name) is None:
            self.cases[full_name] = test_case
        else:
            raise LisaException(f"duplicate test class name: {full_name}")

        # this should be None in current observation.
        # the methods are loadded prior to test class
        # in case logic is changed, so keep this logic
        #   to make two collection consistent.
        class_name = full_name.split(".")[0]
        test_suite = self.suites.get(class_name)
        if test_suite is not None:
            self._log.debug(f"add case '{test_case.name}' to suite '{test_suite.name}'")
            self._add_case_to_suite(test_suite, test_case)

    def _add_case_to_suite(
        self, test_suite: TestSuiteData, test_case: TestCaseData
    ) -> None:
        test_suite.add_case(test_case)
        test_case.suite = test_suite
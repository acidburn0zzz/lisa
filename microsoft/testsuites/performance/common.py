# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from typing import Dict, List

from lisa import notifier
from lisa.environment import Environment
from lisa.notifier import DiskPerformanceMessage, DiskSetupType, DiskType
from lisa.util import dict_to_fields


def handle_and_send_back_results(
    core_count: int,
    disk_count: int,
    environment: Environment,
    disk_setup_type: DiskSetupType,
    disk_type: DiskType,
    test_case_name: str,
    fio_messages: List[DiskPerformanceMessage],
    block_size: int = 4,
) -> None:
    information: Dict[str, str] = environment.get_information()
    for fio_message in fio_messages:
        fio_message = dict_to_fields(information, fio_message)
        fio_message.core_count = core_count
        fio_message.disk_count = disk_count
        fio_message.test_case_name = test_case_name
        fio_message.block_size = block_size
        fio_message.disk_setup_type = disk_setup_type
        fio_message.disk_type = disk_type
        notifier.notify(fio_message)

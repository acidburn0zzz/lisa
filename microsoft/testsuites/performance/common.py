# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from typing import Dict, List

from lisa import notifier
from lisa.environment import Environment
from lisa.notifier import DiskPerformanceMessage, DiskSetupType, DiskType


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
    host_type = information.pop("platform", "")
    host_by = information.pop("location", "")
    host_os = information.pop("host_version", "")
    guest_distro = information.pop("distro_version", "")
    guest_size = information.pop("vmsize", "")
    kernel_version = information.pop("kernel_version", "")
    lis_version = information.pop("lis_version", "")
    for fio_message in fio_messages:
        fio_message.core_count = core_count
        fio_message.disk_count = disk_count
        fio_message.test_case_name = test_case_name
        fio_message.block_size = block_size
        fio_message.disk_setup_type = disk_setup_type
        fio_message.disk_type = disk_type
        fio_message.guest_distro = guest_distro
        fio_message.guest_size = guest_size
        fio_message.host_by = host_by
        fio_message.host_os = host_os
        fio_message.host_type = host_type
        fio_message.kernel_version = kernel_version
        fio_message.lis_version = lis_version
        notifier.notify(fio_message)

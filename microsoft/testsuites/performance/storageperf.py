# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from typing import Any, List

from assertpy import assert_that

from lisa import (
    Logger,
    Node,
    TestCaseMetadata,
    TestSuite,
    TestSuiteMetadata,
    schema,
    search_space,
    simple_requirement,
)
from lisa.environment import Environment
from lisa.features import Disk
from lisa.notifier import DiskPerformanceMessage, DiskSetupType, DiskType
from lisa.tools import FIOMODES, Fdisk, Fio, FIOResult, Lscpu, Mdadm
from microsoft.testsuites.performance.common import handle_and_send_back_results


def _format_disk(
    node: Node,
    disk_list: List[str],
) -> List[str]:
    fdisk = node.tools[Fdisk]
    partition_disks: List[str] = []
    for data_disk in disk_list:
        fdisk.delete_partitions(data_disk)
        partition_disks.append(fdisk.make_partition(data_disk, format=False))
    return partition_disks


def _stop_raid(node: Node) -> None:
    mdadm = node.tools[Mdadm]
    mdadm.stop_raid()


def _make_raid(node: Node, disk_list: List[str]) -> None:
    mdadm = node.tools[Mdadm]
    mdadm.create_raid(disk_list)


@TestSuiteMetadata(
    area="storage",
    category="performance",
    description="""
    This test suite is to validate premium SSD data disks performance of Linux VM using
     fio tool.
    """,
)
class StoragePerformance(TestSuite):  # noqa
    TIME_OUT = 3000

    @TestCaseMetadata(
        description="""
        This test case uses fio to test data disk performance with 4K block size.
        """,
        priority=3,
        timeout=TIME_OUT,
        requirement=simple_requirement(
            min_core_count=72,
            disk=schema.DiskOptionSettings(
                disk_type=schema.DiskType.PremiumSSDLRS,
                data_disk_iops=5000,
                data_disk_count=search_space.IntRange(min=16),
            ),
        ),
    )
    def perf_premium_datadisks_4k(self, node: Node, environment: Environment) -> None:
        self._perf_premium_datadisks(
            node, environment, test_case_name="perf_premium_datadisks_4k"
        )

    @TestCaseMetadata(
        description="""
        This test case uses fio to test data disk performance using 1024K block size.
        """,
        priority=3,
        timeout=TIME_OUT,
        requirement=simple_requirement(
            min_core_count=72,
            disk=schema.DiskOptionSettings(
                disk_type=schema.DiskType.PremiumSSDLRS,
                data_disk_iops=5000,
                data_disk_count=search_space.IntRange(min=16),
            ),
        ),
    )
    def perf_premium_datadisks_1024k(
        self, node: Node, environment: Environment
    ) -> None:
        self._perf_premium_datadisks(
            node,
            environment,
            block_size=1024,
            test_case_name="perf_premium_datadisks_4k",
        )

    def _perf_premium_datadisks(
        self,
        node: Node,
        environment: Environment,
        test_case_name: str,
        block_size: int = 4,
    ) -> None:
        disk = node.features[Disk]
        data_disks = disk.get_raw_data_disks()
        disk_count = len(data_disks)
        assert_that(disk_count).described_as(
            "At least 1 data disk for fio testing."
        ).is_greater_than(0)
        partition_disks = _format_disk(node, data_disks)
        print(partition_disks)
        _stop_raid(node)
        _make_raid(node, partition_disks)
        filename = "/dev/md0"
        cpu = node.tools[Lscpu]
        core_count = cpu.get_core_count()
        start_qdepth = 1
        max_qdepth = 1024
        numjobiterator = 0
        fio_result_list: List[FIOResult] = []
        fio = node.tools[Fio]
        num_jobs = [1, 1, 2, 2, 4, 4, 8, 8, 8, 16, 16, 16]
        for mode in FIOMODES:
            qdepth = start_qdepth
            numjobindex = 0
            while qdepth <= max_qdepth:
                numjob = num_jobs[numjobindex]
                iodepth = int(qdepth / numjob)
                fio_result = fio.launch(
                    name=f"iteration{numjobiterator}",
                    filename=filename,
                    size_gb=1024,
                    block_size=f"{block_size}K",
                    mode=mode.name,
                    gtod_reduce=False,
                    iodepth=int(iodepth),
                    numjob=numjob,
                    overwrite=True,
                )
                fio_result_list.append(fio_result)
                qdepth = qdepth * 2
                numjobindex += 1
                numjobiterator += 1
        fio_messages: List[DiskPerformanceMessage] = fio.create_performance_messages(
            fio_result_list
        )
        handle_and_send_back_results(
            core_count,
            disk_count,
            environment,
            DiskSetupType.raid0,
            DiskType.premiumssd,
            test_case_name,
            fio_messages,
            block_size,
        )

    def after_case(self, log: Logger, **kwargs: Any) -> None:
        node: Node = kwargs.pop("node")
        _stop_raid(node)

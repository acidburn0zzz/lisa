# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from __future__ import annotations

from typing import Dict

from lisa import (
    BadEnvironmentStateException,
    Logger,
    Node,
    SkippedException,
    TestCaseMetadata,
    TestSuite,
    TestSuiteMetadata,
    simple_requirement,
)
from lisa.tools import Cat, Dmesg, Echo, Lscpu, Lsvmbus, Uname


class CPUState:
    OFFLINE: str = "0"
    ONLINE: str = "1"


@TestSuiteMetadata(
    area="cpu",
    category="functional",
    description="""
    This test suite is used to run cpu related tests.
    """,
)
class CPUSuite(TestSuite):
    @TestCaseMetadata(
        description="""
            This test will check cpu online and offline.

            Steps :
            1. skip test case when kernel doesn't support cpu hotplug.
            2. when kernel version is >= 5.8 and vmbus version is >= 4.1, code supports
             to set which cpu vmbus channel interrupts can be assigned to, by setting
             the cpu number to the file
             /sys/bus/vmbus/devices/<device id>/channels/<channel id>/cpu.
             to make sure all cpus except cpu 0 are in idle state.
                2.1 save the raw cpu number for each channel for restoring later.
                2.2 set all vmbus channel interrupts go into cpu 0.
            3. get in used cpu. if the kernel supports to reassign vmbus channels target
             cpu, now the in used cpu is 0.
            4. exclude the in used cpu from all cpu list to get cpu set which can be
             offline and online.
            5. skip testing when there is no idle cpu can be set offline and online.
            6. set idle cpu offline then back to online.
            7. restore the cpu vmbus channel target cpu back to the original state.
            """,
        priority=3,
        requirement=simple_requirement(
            min_core_count=32,
        ),
    )
    def verify_cpu_online_offline(self, node: Node, log: Logger) -> None:
        try:
            # 1. skip test case when kernel doesn't support cpu hotplug.
            uname = node.tools[Uname]
            kernel_version = uname.get_linux_information().kernel_version
            config_path = f"/boot/config-{kernel_version}"
            result = node.execute(
                f"grep CONFIG_HOTPLUG_CPU=y {config_path}", shell=True
            )
            if result.exit_code != 0:
                raise SkippedException("This distro doesn't support cpu hot plug.")

            # 2. when kernel version is >= 5.8 and vmbus version is >= 4.1, code
            #  supports to set which cpu vmbus channel interrupts can be assigned to,
            #  by setting the cpu number to the file
            #  /sys/bus/vmbus/devices/<device id>/channels/<channel id>/cpu.
            #  to make sure all cpus except cpu 0 are in idle state.
            dmesg = node.tools[Dmesg]
            lsvmbus = node.tools[Lsvmbus]
            vmbus_version = dmesg.get_vmbus_version()
            file_path_list: Dict[str, str] = {}
            if kernel_version >= "5.8.0" and vmbus_version >= "4.1.0":
                # 2.1 save the raw cpu number for each channel for restoring later.
                channels = lsvmbus.get_device_channels_from_lsvmbus(force_run=True)
                for channel in channels:
                    for channel_vp_map in channel.channel_vp_map:
                        target_cpu = channel_vp_map.target_cpu
                        if target_cpu == "0":
                            continue
                        file_path_list[
                            self._get_interrupts_assigned_to_cpu(
                                channel.device_id, channel_vp_map.rel_id
                            )
                        ] = target_cpu
                # 2.2 set all vmbus channel interrupts go into cpu 0.
                self._set_cpu_interrupts_assigned_to(file_path_list, node, "0")

            # 3. get cpu set which vmbus channel interrupts assigned to. if the kernel
            #  supports to reassign vmbus channels target cpu, now the in used cpu is 0.
            channels = lsvmbus.get_device_channels_from_lsvmbus(force_run=True)
            cpu_in_used = set()
            for channel in channels:
                for channel_vp_map in channel.channel_vp_map:
                    target_cpu = channel_vp_map.target_cpu
                    if target_cpu == "0":
                        continue
                    cpu_in_used.add(target_cpu)

            # 4. exclude the in used cpu from all cpu list to get cpu set which can be
            #  offline and online.
            cpu_count = node.tools[Lscpu].get_core_count()
            log.debug(f"{cpu_count} CPU cores detected...")
            all_cpu = list(range(1, cpu_count))
            idle_cpu = [x for x in all_cpu if str(x) not in cpu_in_used]

            # 5. skip testing when there is no idle cpu can be set offline and online.
            if 0 == len(idle_cpu):
                raise SkippedException("no idle cpu can be set offline or online.")

            # 6. set idle cpu offline then back to online.
            for target_cpu in idle_cpu:
                log.debug(f"checking cpu{target_cpu} on /sys/device/....")
                result = self._set_cpu_state(target_cpu, CPUState.OFFLINE, node)
                if result:
                    # bring cpu back to it's original state
                    reset = self._set_cpu_state(target_cpu, CPUState.ONLINE, node)
                    exception_message = (
                        f"expected cpu{target_cpu} state: {CPUState.ONLINE}(online), "
                        f"actual state: {CPUState.OFFLINE}(offline)."
                    )
                    if not reset:
                        raise BadEnvironmentStateException(
                            exception_message,
                            f"the test failed leaving cpu{target_cpu} in a bad state.",
                        )
        finally:
            # 7. restore the cpu vmbus channel target cpu back to the original state.
            self._restore_cpu_interrupts_assigned_to(file_path_list, node)

    def _get_cpu_config_file(self, cpu_id: str) -> str:
        return f"/sys/devices/system/cpu/cpu{cpu_id}/online"

    def _get_interrupts_assigned_to_cpu(self, device_id: str, channel_id: str) -> str:
        return f"/sys/bus/vmbus/devices/{device_id}/channels/{channel_id}/cpu"

    def _set_cpu_interrupts_assigned_to(
        self,
        path_cpu: Dict[str, str],
        node: Node,
        target_cpu: str = "0",
    ) -> None:
        for path, _ in path_cpu.items():
            file_path = node.get_pure_path(path)
            node.tools[Echo].write_to_file(
                target_cpu, node.get_pure_path(file_path), sudo=True
            )

    def _restore_cpu_interrupts_assigned_to(
        self,
        path_cpu: Dict[str, str],
        node: Node,
    ) -> None:
        for path, target_cpu in path_cpu.items():
            file_path = node.get_pure_path(path)
            node.tools[Echo].write_to_file(
                target_cpu, node.get_pure_path(file_path), sudo=True
            )

    def _set_cpu_state(self, cpu_id: str, state: str, node: Node) -> bool:
        file_path = self._get_cpu_config_file(cpu_id)
        node.tools[Echo].write_to_file(state, node.get_pure_path(file_path), sudo=True)
        result = node.tools[Cat].read(file_path, force_run=True, sudo=True)
        return result == state

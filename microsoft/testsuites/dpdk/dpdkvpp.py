# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
import time
from typing import List, Type
from lisa.executable import Tool
from lisa.tools import Git, Gcc, Make, Wget
from lisa.operating_system import Fedora, Ubuntu, Redhat
from lisa.util import UnsupportedDistroException
from pathlib import PurePath


class DpdkVpp(Tool):

    VPP_SRC_LINK = "https://github.com/FDio/vpp.git"
    REPO_DIR = "nffgo"

    redhat_packages: List[str] = [
        "kernel-devel-$(uname -r)",
        "librdmacm-devel",
        "redhat-lsb",
        "glibc-static",
        "apr-devel",
        "numactl-devel.x86_64",
        "libmnl-devel",
        "check",
        "check-devel",
        "boost",
        "boost-devel",
        "selinux-policy",
        "selinux-policy-devel",
        "ninja-build",
        "libuuid-devel",
        "mbedtls-devel",
        "yum-utils",
        "openssl-devel",
        "python36-devel",
        "cmake3",
        "asciidoc",
        "libffi-devel",
        "chrpath",
        "yum-plugin-auto-update-debug-info",
        "java-1.8.0-openjdk-devel",
    ]

    @property
    def command(self) -> str:
        return "vpp"

    @property
    def dependencies(self) -> List[Type[Tool]]:
        return [Gcc, Make, Git, Wget]

    def _install(self) -> bool:
        node = self.node
        if isinstance(node.os, Ubuntu):
            node.os.add_repository("ppa:canonical-server/server-backports")
            node.os.install_packages(["python-cffi", "python-pycparser"])
        elif isinstance(node.os, Redhat):
            node.os.install_epel()
            node.os.group_install_packages("Development Tools")

        else:
            raise UnsupportedDistroException(self.node.os)
        git = node.tools[Git]
        self.repo = git.clone(
            self.VPP_SRC_LINK, node.working_path, dir_name=self.REPO_DIR
        )
        self.make = node.tools[Make]

        self.make.make("install-deps", self.repo)
        return True

    def make_and_run_tests(self) -> None:
        # NOTE: These unit tests take more than an hour to run
        self.make.make("install-deps", self.repo)
        self.make.make(
            "build",
            self.repo,
        )
        self.make.make("test", self.repo, timeout=6000)

    def make_distro_package(self) -> None:
        node = self.node
        if isinstance(node.os, Ubuntu):
            package_type = "deb"
        elif isinstance(node.os, Fedora):
            package_type = "rpm"
        else:
            raise UnsupportedDistroException(node.os)

        make_args = (
            f"pkg-{package_type} vpp_uses_dpdk_mlx4_pmd=yes "
            "vpp_uses_dpdk_mlx5_pmd=yes DPDK_MLX4_PMD=y DPDK_MLX5_PMD=y "
            "DPDK_MLX5_PMD_DLOPEN_DEPS=y DPDK_MLX4_PMD_DLOPEN_DEPS=y"
        )

        self.make.make(make_args, self.repo, timeout=1200)
        build_root = self.repo.joinpath("build-root")
        if isinstance(node.os, Ubuntu):
            node.execute(
                "dpkg -i *.deb",
                shell=True,
                cwd=build_root,
                sudo=True,
                expected_exit_code=0,
                expected_exit_code_failure_message="couldn't install dpkgs",
            )
            # the package name doesn't match the added apt entry so our regular installation
            # doesn't work with this case. This was the trick used in v2.
            node.execute(
                "apt --fix-broken -y install",
                sudo=True,
                expected_exit_code=0,
                expected_exit_code_failure_message="apt fix broken failed",
            )
        else:
            raise UnsupportedDistroException(
                os=node.os,
                message=(
                    "VPP install for lisa has not been implemented for this platform"
                ),
            )

        node.log.info(node.execute_async("vpp -c /etc/vpp/startup.conf", sudo=True))
        time.sleep(5)
        node.log.info(node.execute("vppctl show int", sudo=True).stdout)

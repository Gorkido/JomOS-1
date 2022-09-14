import re
import sys
import os
import logging
import utils
from rich.logging import RichHandler
from rich import print
from rich.panel import Panel

FORMAT = "%(message)s"
logging.basicConfig(
    level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

log = logging.getLogger("rich")

# Options, TODO: make them a cli parameter

DRYRUN = 1
THIRDPARTYREPOS = 1
THEMING_ = 1

if DRYRUN:
    log.info("DRYRUN mode is on")

USERNAME = ("liveuser" if os.path.exists("/home/liveuser")
            else utils.term("whoami").replace("\n", ""))

HOMEDIR = "/home/" + USERNAME
PHYSMEMRAW = utils.term("grep MemTotal /proc/meminfo")

# Get ram amount in kb and convert to gb with floor division
PHYSMEMGB = int(re.sub("[^0-9]", "", PHYSMEMRAW)) // 1048576

SWAPPINESS = min((200 // PHYSMEMGB) * 2, 150)
VFSCACHEPRESSURE = int(max(min(SWAPPINESS*1.25, 125), 32))

V3_SUPPORT = utils.term(
    "/lib/ld-linux-x86-64.so.2 --help | grep \"x86-64-v3 (supported, searched)\"").find("86-64-v3 (supported, searched)")

zram_state = utils.term("swapon -s")
if zram_state.find("zram") == 0:
    log.info("This system already has zram")
elif zram_state.find("dev") == 0:
    log.info("This system already has physical swap")
else:
    log.info("System has no swap")

zswap_state = utils.term("cat /sys/module/zswap/parameters/enabled")
log.info(zswap_state)

if zswap_state == "N\n":
    log.info("Zswap is disabled")
else:
    log.warning(
        "Zswap is enabled, please disable Zswap if you want to use zram.")

# TODO: add check for physical swap and zswap parameters

GENERIC = utils.read_file_lines("scripts/generic")
THEMING = utils.read_file_lines("scripts/theming")
REPOSV3 = utils.read_file_lines("scripts/repos-v3")
REPOS = utils.read_file_lines("scripts/repos")


TWEAKLIST = [
    f"vm.swappiness = {SWAPPINESS}",
    f"vm.vfs_cache_pressure = {VFSCACHEPRESSURE}",
    "vm.page-cluster = 0",
    "vm.dirty_ratio = 10",
    "vm.dirty_background_ratio = 5",
    "net.core.default_qdisc = cake",
    "net.ipv4.tcp_congestion_control = bbr2",
    "net.ipv4.tcp_fastopen = 3",
    "kernel.nmi_watchdog = 0"
]

ABOUT = """
JomOS is a meta Linux distribution which allows users to mix-and-match
well tested configurations and optimizations with little to no effort 
 
JomOS integrates these configurations into one largely cohesive system.

[red]
Continuing will:
- Convert existing installation into JomOS
[/red]
"""

print(Panel.fit(ABOUT, title="JomOS alpha 0.1"))

confirmation = input(
    'Please type "Confirm" without quotes at the prompt to continue: \n'
)

if confirmation != "Confirm":
    log.warning("Warning not copied exactly.")
    sys.exit()

log.info(
    f"USERNAME: \"{USERNAME}\"\nRAM AMOUNT: {PHYSMEMGB}\nCALCULATED SWAPPINESS: {SWAPPINESS}\nCALCULATED VFS_CACHE_PRESSURE: {VFSCACHEPRESSURE}"
)


whiskermenupath = utils.term(
    "ls " + HOMEDIR + "/.config/xfce4/panel/whiskermenu-*.rc").replace("\n", "")

# Copy system configs for necessary modifications
utils.term("cp /etc/makepkg.conf ./etc/makepkg.conf")
utils.term("cp /etc/pacman.conf ./etc/pacman.conf")
utils.term("cp /etc/mkinitcpio.conf ./etc/mkinitcpio.conf")

FILELIST = utils.returnfiles("./etc/")

# Modify configuration files
try:
    if not DRYRUN:
        utils.replace_in_file(
            "./etc/makepkg.conf",
            "#MAKEFLAGS=\"-j2\"",
            "MAKEFLAGS=\"-j$(nproc)\""
        )

        utils.replace_in_file("./etc/sysctl.d/99-JomOS-settings.conf",
                              "vm.swappiness = 50",
                              "vm.swappiness = " + str(SWAPPINESS)
                              )

        utils.replace_in_file(
            "./etc/sysctl.d/99-JomOS-settings.conf",
            "vm.vfs_cache_pressure = 50",
            "vm.vfs_cache_pressure = " + str(VFSCACHEPRESSURE)
        )

        mkinitcpio = utils.read_file("./etc/mkinitcpio.conf")
        if mkinitcpio.find("COMPRESSION") == 0 and mkinitcpio.find("#COMPRESSION_OPTIONS") == 0:
            mkinitcpio = re.sub("COMPRESSION=\"(.*?)\"",
                                "COMPRESSION=\"zstd\"", str(mkinitcpio))
            mkinitcpio.replace("#COMPRESSION_OPTIONS=()",
                               "COMPRESSION_OPTIONS=(-2)")

        utils.write_file("./etc/mkinitcpio.conf", mkinitcpio)

        if V3_SUPPORT and THIRDPARTYREPOS:
            utils.replace_in_file(
                "./etc/pacman.conf",
                "[core]\nInclude = /etc/pacman.d/mirrorlist",
                "[cachyos-v3]\nInclude = /etc/pacman.d/cachyos-v3-mirrorlist\n[cachyos]\nInclude = /etc/pacman.d/cachyos-mirrorlist\n\n[core]Include = /etc/pacman.d/mirrorlist"
            )
        elif THIRDPARTYREPOS:
            utils.replace_in_file(
                "./etc/pacman.conf",
                "[core]\nInclude = /etc/pacman.d/mirrorlist",
                "[cachyos]\nInclude = /etc/pacman.d/cachyos-mirrorlist\n\n[core]Include = /etc/pacman.d/mirrorlist"
            )

except Exception:
    # TODO: proper error handling
    log.error("Error when modifying configurations")
else:
    log.info("File /etc/sysctl.d/99-JomOS-settings.conf modified")
    log.info("File /etc/makepkg.conf modified")
    log.info("File /etc/mkinitcpio.conf modified")
    log.info("File /etc/pacman.conf modified")

if V3_SUPPORT:
    log.info("86-64-v3 (supported, searched)")

if not DRYRUN:

    utils.install_dir("./etc", "/", "-D -o root -g root -m 644")

    for file in FILELIST:
        filecontents = utils.read_file(file)
        # Check file length, dont show it if its longer than 2000 characters
        if len(filecontents) < 2000:
            log.info(f"Installed file: {file}\n{filecontents}")
        else:
            log.info("Installed file: " + file +
                     "\n(File too long to display)")

    # Generic commands that arent specific to anything
    for command in GENERIC:
        log.info("Executing command: " + command)
        utils.term(command)

    # Adding third party repositories
    if V3_SUPPORT and THIRDPARTYREPOS:
        for command in REPOSV3:
            log.info("Executing command: " + command)
            utils.term(command)
    elif THIRDPARTYREPOS:
        for command in REPOS:
            log.info("Executing command: " + command)
            utils.term(command)

    # Theming
    if THEMING_:
        for command in THEMING:
            log.info("Executing command: " + command)
            utils.term(command)

    for tweak in TWEAKLIST:
        log.info(tweak)

    if whiskermenupath and THEMING_:
        utils.replace_in_file(
            str(whiskermenupath),
            "button-title=EndeavourOS",
            "button-title=JomOS",
        )

#!/usr/bin/env python3
"""Install, update or remove Klipper Chamber Cooldown.

Run it from the cloned repository:

    python3 install.py              install or update (safe to run again)
    python3 install.py -u           uninstall
    python3 install.py -n           show what would change and change nothing

It moves the clone to the latest release, backs up printer.cfg and moonraker.conf, adds the
include lines to printer.cfg and an update_manager entry to moonraker.conf, copies
examples/cooldown-local.cfg to cooldown-local.cfg for your overrides, and restarts Moonraker and
Klipper unless a print is running or paused. Klipper-Hardware-Controls must already be included in
printer.cfg.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.realpath(__file__))
NAME = "Klipper-Chamber-Cooldown"
DEFAULT_ORIGIN = "https://github.com/IdleStep/Klipper-Chamber-Cooldown.git"
BEGIN = "# >>> %s (added by install.py)" % NAME
END = "# <<< %s" % NAME
SAVE_CONFIG = "#*# <---------------------- SAVE_CONFIG"
HEADER = re.compile(r"^\[([^\]]+)\]")
LOCAL = "cooldown-local.cfg"
HARDWARE = "Klipper-Hardware-Controls"


# --- text edits (pure functions, so they can be tested without a printer) ---

def section_name(line):
    match = HEADER.match(line)
    return match.group(1).strip().lower() if match else None


def include_lines(folder):
    return ["[include %s/cooldown.cfg]" % folder, "[include %s]" % LOCAL]


def has_include(text, folder):
    return re.search(r"^\s*\[include\s+%s/" % re.escape(folder), text, re.M) is not None


def edit_printer_cfg(text, folder):
    """Return (new text, notes): add the include above the SAVE_CONFIG block unless one is there."""
    lines = text.split("\n")
    trailing_newline = lines[-1] == ""
    if trailing_newline:
        lines.pop()
    end = next((i for i, line in enumerate(lines) if line.startswith(SAVE_CONFIG)), len(lines))
    body, tail = lines[:end], lines[end:]
    if has_include("\n".join(body), folder):
        return text, ["printer.cfg already includes %s" % folder]
    while body and body[-1].strip() == "":
        body.pop()
    body += [""] + [BEGIN] + include_lines(folder) + [END]
    if tail:
        body.append("")
    return "\n".join(body + tail) + ("\n" if trailing_newline else ""), ["added the includes for %s" % folder]


def edit_moonraker(text, path, origin, channel):
    """Add [update_manager NAME] unless moonraker.conf has one; return (new text, notes)."""
    lines = text.split("\n")
    if any(section_name(line) == "update_manager " + NAME.lower() for line in lines):
        return text, ["already has an [update_manager %s] section; left as it is "
                      "(if you moved the clone, fix its path by hand)" % NAME]
    block = ["", BEGIN, "[update_manager %s]" % NAME, "type: git_repo", "channel: %s" % channel,
             "path: %s" % path, "origin: %s" % origin, "primary_branch: main", "is_system_service: False",
             "managed_services: klipper", END]
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines + block) + "\n", ["added [update_manager %s]" % NAME]


def remove_block(text):
    """Remove the block this installer added, if it is still there."""
    pattern = re.compile(r"\n?%s\n.*?\n%s\n?" % (re.escape(BEGIN), re.escape(END)), re.S)
    return pattern.sub("", text, count=1)


def release_tags(output):
    """The vMAJOR.MINOR.PATCH tags in `git tag` output, newest first."""
    tags = [t for t in output.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    return sorted(tags, key=lambda t: tuple(int(n) for n in t[1:].split(".")), reverse=True)


# --- the installer ---

class Installer:
    def __init__(self, args):
        self.args = args
        self.dry = args.dry_run
        self.config_dir = os.path.realpath(os.path.expanduser(args.config_dir or default_config_dir()))
        self.printer_cfg = os.path.join(self.config_dir, "printer.cfg")
        self.moonraker_conf = os.path.join(self.config_dir, "moonraker.conf")
        self.folder = os.path.relpath(REPO, self.config_dir).replace(os.sep, "/")
        self.changed = False

    def say(self, message):
        print(("[dry run] " if self.dry else "") + message)

    def git(self, *args):
        result = subprocess.run(["git", "-C", REPO] + list(args), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, universal_newlines=True)
        return result.returncode, result.stdout.strip()

    def check(self, remove):
        """Stop before changing anything if the install could not work."""
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            sys.exit("Run this as your normal user, not root: it edits your config.")
        if not os.path.isdir(self.config_dir):
            sys.exit("The config directory %s was not found. Use -c to point at it." % self.config_dir)
        if self.folder.startswith(".."):
            sys.exit("This clone is not inside %s. Clone it there, so printer.cfg can include it:\n"
                     "    cd %s && git clone %s" % (self.config_dir, self.config_dir, DEFAULT_ORIGIN))
        if not remove and os.path.exists(self.printer_cfg):
            with open(self.printer_cfg) as f:
                if not has_include(f.read(), HARDWARE):
                    sys.exit("printer.cfg does not include %s. Install it first: "
                             "https://github.com/IdleStep/Klipper-Hardware-Controls#install" % HARDWARE)

    def local_file(self, remove):
        """Create cooldown-local.cfg from the example, so the include finds a file. Uninstall keeps it."""
        path = os.path.join(self.config_dir, LOCAL)
        example = os.path.join(REPO, "examples", LOCAL)
        if remove or os.path.exists(path) or not os.path.exists(example):
            return
        self.say("creating %s from examples/%s" % (LOCAL, LOCAL))
        if not self.dry:
            shutil.copyfile(example, path)
        self.changed = True

    def update(self):
        """Move the clone to the latest release (or main with --dev); a clone with changes stays as it is."""
        if self.args.no_update:
            return
        if not os.path.isdir(os.path.join(REPO, ".git")):
            self.say("not a git clone; skipping the update")
            return
        if self.git("status", "--porcelain")[1]:
            self.say("the clone has local changes; not updating it")
            return
        code, _ = self.git("fetch", "--tags", "--quiet", "origin")
        if code != 0:
            self.say("could not reach origin; keeping the version you have")
            return
        before = self.git("rev-parse", "HEAD")[1]
        tags = release_tags(self.git("tag", "--list")[1]) if not self.args.dev else []
        if tags:
            target = tags[0]
            if self.git("merge-base", "--is-ancestor", "HEAD", target)[0] != 0:
                self.say("the clone is ahead of %s; not moving it" % target)
                return
        else:
            target = "main"
        if before == self.git("rev-parse", ("origin/main" if target == "main" else target) + "^{commit}")[1]:
            self.say("the clone is already at %s" % target)
            return
        label = self.git("describe", "--tags", "--always")[1]
        self.say("moving from %s to %s" % (label, target))
        if self.dry:
            return
        if target == "main":
            self.git("checkout", "--quiet", "main")
            code, out = self.git("merge", "--ff-only", "--quiet", "origin/main")
        else:
            code, out = self.git("checkout", "--quiet", target)
        if code != 0:
            print("Could not move the clone to %s: %s" % (target, out))
            return
        if self.git("rev-parse", "HEAD")[1] != before:
            self.changed = True

    def edit_file(self, path, editor, label):
        if not os.path.exists(path):
            return None
        with open(path) as f:
            old = f.read()
        new, notes = editor(old)
        for note in notes:
            self.say("%s: %s" % (label, note))
        if new != old:
            backup = path + ".before-" + NAME.lower()
            if not os.path.exists(backup):  # keep the first one: it is the file as you had it
                self.say("backing up %s to %s" % (os.path.basename(path), os.path.basename(backup)))
                if not self.dry:
                    shutil.copy2(path, backup)
            if not self.dry:
                with open(path, "w") as f:
                    f.write(new)
            self.changed = True
            return True
        return False

    def configs(self, remove):
        if not os.path.exists(self.printer_cfg):
            self.say("no printer.cfg at %s; add the include by hand (see README.md)" % self.printer_cfg)
        elif remove:
            self.edit_file(self.printer_cfg, lambda t: (remove_block(t), [
                "removed the include" if BEGIN in t else
                "no block added by install.py; delete the include of %s by hand if you want it gone" % NAME]),
                           "printer.cfg")
        else:
            self.edit_file(self.printer_cfg, lambda t: edit_printer_cfg(t, self.folder), "printer.cfg")
        if not os.path.exists(self.moonraker_conf):
            self.say("no moonraker.conf at %s; skipping the update_manager entry" % self.moonraker_conf)
            return
        if remove:
            self.edit_file(self.moonraker_conf, lambda t: (remove_block(t), [
                "removed the update_manager block" if BEGIN in t else
                "no block added by install.py; delete [update_manager %s] by hand if you want it gone" % NAME]),
                           "moonraker.conf")
            return
        home = os.path.expanduser("~")
        path = REPO.replace(home, "~", 1) if REPO.startswith(home + os.sep) else REPO
        origin = self.git("remote", "get-url", "origin")[1] or DEFAULT_ORIGIN
        channel = "dev" if self.args.dev else "stable"
        self.edit_file(self.moonraker_conf, lambda t: edit_moonraker(t, path, origin, channel), "moonraker.conf")

    def api(self, path, post=False):
        request = urllib.request.Request(self.args.moonraker_url + path, method="POST" if post else "GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def service_names(self):
        """This instance's Moonraker and Klipper unit names; with several printers on one host they are not
        the defaults, and restarting the defaults would restart the wrong printer."""
        try:
            ids = self.api("/machine/system_info")["result"]["system_info"]["instance_ids"]
            return ids["moonraker"], ids["klipper"]
        except (urllib.error.URLError, OSError, KeyError, ValueError, TypeError):
            return "moonraker", "klipper"

    def restart(self):
        if not self.changed:
            self.say("nothing changed, so nothing was restarted")
            return
        if self.args.no_restart or self.dry:
            self.say("not restarting; restart Moonraker and Klipper yourself to load the changes")
            return
        try:
            state = self.api("/printer/objects/query?print_stats")["result"]["status"]["print_stats"]["state"]
        except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
            print("Could not read the print state from Moonraker at %s (%s). Restart Moonraker and Klipper "
                  "yourself." % (self.args.moonraker_url, e))
            return
        if state in ("printing", "paused"):
            print("A print is running or paused, so nothing was restarted. Restart Klipper when it is done.")
            return
        moonraker, klipper = self.service_names()
        print("restarting %s, then %s" % (moonraker, klipper))
        try:
            self.api("/machine/services/restart?service=" + urllib.parse.quote(moonraker), post=True)
            for _ in range(30):
                time.sleep(1)
                try:
                    self.api("/server/info")
                    break
                except (urllib.error.URLError, OSError, ValueError):
                    continue
            self.api("/machine/services/restart?service=" + urllib.parse.quote(klipper), post=True)
        except (urllib.error.URLError, OSError, ValueError) as e:
            print("Restart failed (%s). Restart Moonraker and Klipper yourself." % e)

    def run(self, remove):
        self.check(remove)
        if not remove:
            self.update()
        self.local_file(remove)
        self.configs(remove)
        self.restart()
        if remove:
            print("\nChamber Cooldown is removed from your configuration. The clone in %s and your %s are "
                  "still there; delete them if you like." % (REPO, LOCAL))
        else:
            print("\nDone. In the console, try:  COOLDOWN_SELECT MATERIAL=ASA   then   START_COOLDOWN")


def default_config_dir():
    """The folder this clone sits in when it holds a printer.cfg, else the usual Moonraker one."""
    parent = os.path.dirname(REPO)
    return parent if os.path.exists(os.path.join(parent, "printer.cfg")) else "~/printer_data/config"


def main():
    parser = argparse.ArgumentParser(description="Install, update or remove Klipper Chamber Cooldown.")
    parser.add_argument("-c", "--config-dir", help="config directory (default: the folder holding this clone, "
                                                   "else ~/printer_data/config)")
    parser.add_argument("--moonraker-url", default="http://localhost:7125", help="Moonraker address")
    parser.add_argument("-u", "--uninstall", action="store_true", help="remove the include and update entry")
    parser.add_argument("-n", "--dry-run", action="store_true", help="show what would change, change nothing")
    parser.add_argument("-r", "--no-restart", action="store_true", help="do not restart Moonraker and Klipper")
    parser.add_argument("--dev", action="store_true", help="follow main instead of the latest release")
    parser.add_argument("--no-update", action="store_true", help="do not move the clone to a newer version")
    args = parser.parse_args()
    Installer(args).run(args.uninstall)


if __name__ == "__main__":
    main()

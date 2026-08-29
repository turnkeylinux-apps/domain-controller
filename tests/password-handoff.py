#!/usr/bin/python3
"""Focused regression checks for Domain Controller password handoff."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import types


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLED_DOMAIN_SCRIPT = Path('/usr/lib/inithooks/bin/domain-controller.py')
INSTALLED_FIRSTBOOT_SCRIPT = Path(
    '/usr/lib/inithooks/firstboot.d/40domain-controller')
DOMAIN_SCRIPT = Path(os.environ.get(
    'TKL_DOMAIN_SCRIPT',
    INSTALLED_DOMAIN_SCRIPT if INSTALLED_DOMAIN_SCRIPT.exists()
    else REPO_ROOT / 'overlay/usr/lib/inithooks/bin/domain-controller.py'))
FIRSTBOOT_SCRIPT = Path(os.environ.get(
    'TKL_FIRSTBOOT_SCRIPT',
    INSTALLED_FIRSTBOOT_SCRIPT if INSTALLED_FIRSTBOOT_SCRIPT.exists()
    else REPO_ROOT / 'overlay/usr/lib/inithooks/firstboot.d/40domain-controller'))
SECRET = 'turnkey-password-regression-only'


def fail(message):
    raise SystemExit(f'FAIL: {message}')


def load_domain_module():
    dialog_module = types.ModuleType('libinithooks.dialog_wrapper')
    dialog_module.Dialog = object
    package = types.ModuleType('libinithooks')
    package.__path__ = []
    sys.modules['libinithooks'] = package
    sys.modules['libinithooks.dialog_wrapper'] = dialog_module

    spec = importlib.util.spec_from_file_location(
        'turnkey_domain_controller', DOMAIN_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_fake_samba(result, emitted):
    calls = []

    def samba_tool(*args):
        calls.append(args)
        print(emitted)
        return result

    samba = types.ModuleType('samba')
    samba.__path__ = []
    netcmd = types.ModuleType('samba.netcmd')
    netcmd.__path__ = []
    main = types.ModuleType('samba.netcmd.main')
    main.samba_tool = samba_tool
    sys.modules['samba'] = samba
    sys.modules['samba.netcmd'] = netcmd
    sys.modules['samba.netcmd.main'] = main
    return calls


def check_wrapper():
    wrapper = FIRSTBOOT_SCRIPT.read_text(encoding='utf-8')
    if '--pass="$APP_PASS"' in wrapper:
        fail('firstboot still places APP_PASS in argv')
    if 'printf \'%s\' "$APP_PASS" |' not in wrapper:
        fail('firstboot does not pipe APP_PASS on stdin')
    if '--pass-stdin' not in wrapper:
        fail('firstboot does not select the stdin password contract')


def check_provision(module, result, emitted):
    calls = install_fake_samba(result, emitted)
    safe_command = [
        'samba-tool', 'domain', 'provision', '--realm=EXAMPLE.INVALID',
        '--domain=EXAMPLE',
    ]
    console = io.StringIO()
    with contextlib.redirect_stdout(console):
        status, output = module.run_samba_provision(safe_command, SECRET)

    expected = 0 if result is None else result
    if status != expected:
        fail(f'in-process provision returned {status}, expected {expected}')
    if calls != [tuple(safe_command[1:] + [f'--adminpass={SECRET}'])]:
        fail('in-process provision received unexpected arguments')
    if SECRET in output or SECRET in console.getvalue():
        fail('provision output retained the administrator password')
    if '<REDACTED>' not in output:
        fail('provision output did not redact a reflected password')


def check_kerberos_readiness(module):
    calls = []
    sleeps = []
    results = iter([
        types.SimpleNamespace(returncode=1, stderr='KDC not ready'),
        types.SimpleNamespace(returncode=0, stderr=''),
    ])

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return next(results)

    original_run = module.subprocess.run
    original_sleep = module.time.sleep
    module.subprocess.run = fake_run
    module.time.sleep = sleeps.append
    try:
        module.obtain_kerberos_ticket('administrator', SECRET, attempts=3,
                                     delay=0.25)
    finally:
        module.subprocess.run = original_run
        module.time.sleep = original_sleep

    if len(calls) != 2 or sleeps != [0.25]:
        fail('Kerberos readiness retry did not stop after success')
    for command, kwargs in calls:
        if command != ['kinit', 'administrator'] or SECRET in command:
            fail('Kerberos retry placed the password in argv')
        if kwargs.get('input') != SECRET:
            fail('Kerberos retry did not pass the password on stdin')

    def reflected_failure(command, **kwargs):
        return types.SimpleNamespace(
            returncode=1, stderr=f'failure reflected {SECRET}')

    module.subprocess.run = reflected_failure
    module.time.sleep = lambda delay: None
    try:
        try:
            module.obtain_kerberos_ticket('administrator', SECRET,
                                         attempts=1, delay=0)
        except RuntimeError as error:
            message = str(error)
        else:
            fail('Kerberos readiness terminal failure was not reported')
    finally:
        module.subprocess.run = original_run
        module.time.sleep = original_sleep

    if SECRET in message or '<REDACTED>' not in message:
        fail('Kerberos readiness failure did not redact the password')


def main():
    check_wrapper()
    module = load_domain_module()
    check_provision(module, None, f'created domain with {SECRET}')
    check_provision(module, 17, f'provision failed for {SECRET}')
    check_kerberos_readiness(module)
    print('PASS: password uses stdin with redacted provision and KDC retry')


if __name__ == '__main__':
    main()

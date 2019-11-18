import argparse
import atexit
import calendar
import codecs
import collections
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import fileinput
from functools import wraps
import hashlib
import inspect
import json
import logging
import multiprocessing
from multiprocessing import Pool
import operator
import os
from os.path import expanduser
import pickle
import platform
import random
import re
import select
import shutil
import smtplib
import socket
import subprocess
import sys
import threading
import time

class Util:
    @staticmethod
    def execute(cmd, show_cmd=True, exit_on_error=True, return_out=False, show_duration=False, dryrun=False, log_file=''):
        orig_cmd = cmd
        if show_cmd:
            Util.cmd(orig_cmd)

        if Util.HOST_OS == 'windows':
            cmd = '%s 2>&1' % cmd
        else:
            cmd = 'bash -o pipefail -c "%s 2>&1' % cmd
        if log_file:
            cmd += ' | tee -a %s' % log_file
        if not Util.HOST_OS == 'windows':
            cmd += '; (exit ${PIPESTATUS})"'

        if show_duration:
            timer = Timer()

        if dryrun:
            result = [0, '']
        elif return_out:
            process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out, err) = process.communicate()
            ret = process.returncode
            result = [ret, (out + err).decode('utf-8')]
        else:
            ret = os.system(cmd)
            result = [int(ret / 256), '']

        if show_duration:
            Util.info('%s was spent to execute command "%s" in function "%s"' % (timer.stop(), orig_cmd, inspect.stack()[1][3]))

        if ret:
            if exit_on_error:
                Util.error('Failed to execute command "%s"' % orig_cmd)
            else:
                Util.warning('Failed to execute command "%s"' % orig_cmd)

        return result

    @staticmethod
    def _msg(msg, show_strace=False):
        m = inspect.stack()[1][3].upper()
        if show_strace:
            m += ', File "%s", Line: %s, Function %s' % inspect.stack()[2][1:4]
        m = '[' + m + '] ' + msg
        print(m)

    @staticmethod
    def info(msg):
        Util._msg(msg)

    @staticmethod
    def warning(msg):
        Util._msg(msg, show_strace=True)

    @staticmethod
    def cmd(msg):
        Util._msg(msg)

    @staticmethod
    def debug(msg):
        Util._msg(msg)

    @staticmethod
    def strace(msg):
        Util._msg(msg)

    @staticmethod
    def error(msg, abort=True, error_code=1):
        Util._msg(msg, show_strace=True)
        if abort:
            quit(error_code)

    @staticmethod
    def chdir(dir_path, verbose=False):
        if verbose:
            Util.info('Enter ' + dir_path)
        os.chdir(dir_path)

    @staticmethod
    def get_dir(path):
        return os.path.split(os.path.realpath(path))[0]

    @staticmethod
    def ensure_dir(dir):
        if not os.path.exists(dir):
            os.makedirs(dir)

    @staticmethod
    def ensure_nodir(dir):
        if os.path.exists(dir):
            shutil.rmtree(dir)

    @staticmethod
    def ensure_file(file_path):
        Util.ensure_dir(os.path.dirname(os.path.abspath(file_path)))
        if not os.path.exists(file_path):
            open(file_path, 'w').close()

    @staticmethod
    def ensure_nofile(file_path):
        if not os.path.exists(file_path):
            return

        os.remove(file_path)

    @staticmethod
    def pkg_installed(pkg):
        cmd = 'dpkg -s ' + pkg
        result = Util.execute(cmd, return_out=True, show_cmd=False)
        if result[0]:
            return False
        else:
            return True

    @staticmethod
    def install_pkg(pkg):
        if Util.pkg_installed(pkg):
            return True
        else:
            Util.info('Package ' + pkg + ' is installing...')
            cmd = 'sudo apt-get install --force-yes -y ' + pkg
            result = Util.execute(cmd)
            if result[0]:
                Util.warning('Package ' + pkg + ' installation failed')
                return False
            else:
                return True

    @staticmethod
    def ensure_pkg(pkgs):
        ret = True
        pkg_list = pkgs.split(' ')
        for pkg in pkg_list:
            ret &= Util.install_pkg(pkg)

        return ret

    @staticmethod
    def read_file(file_path):
        if not os.path.exists(file_path):
            return []

        f = open(file_path)
        lines = [line.rstrip('\n') for line in f]
        if len(lines) > 0:
            while (lines[-1] == ''):
                del lines[-1]
        f.close()
        return lines

    @staticmethod
    def write_file(file_path, lines):
        Util.ensure_file(file_path)
        f = open(file_path, 'w')
        for line in lines:
            f.write(line + '\n')
            print(line)
        f.close()

    @staticmethod
    def get_datetime(format='%Y%m%d%H%M%S'):
        return time.strftime(format, time.localtime())

    @staticmethod
    def get_env(env):
        return os.getenv(env)

    @staticmethod
    def set_env(env, value):
        if value:
            os.environ[env] = value

    @staticmethod
    def prepend_path(path):
        paths = Util.get_env('PATH').split(Util.ENV_SPLITTER)
        new_paths = path.split(Util.ENV_SPLITTER)

        for tmp_path in paths:
            if tmp_path not in new_paths:
                new_paths.append(tmp_path)

        Util.set_env('PATH', Util.ENV_SPLITTER.join(new_paths))

    @staticmethod
    def remove_path(path):
        paths = Util.get_env('PATH').split(Util.ENV_SPLITTER)
        for tmp_path in paths:
            if tmp_path == path:
                paths.remove(tmp_path)

        Util.set_env('PATH', Util.ENV_SPLITTER.join(paths))

    @staticmethod
    def has_depot_tools_in_path():
        paths = Util.get_env('PATH').split(Util.ENV_SPLITTER)
        for tmp_path in paths:
            if re.search('depot_tools$', tmp_path):
                return True
        else:
            return False

    @staticmethod
    def set_proxy(address, port):
        http_proxy = 'http://%s:%s' % (address, port)
        https_proxy = 'https://%s:%s' % (address, port)
        Util.set_env('http_proxy', http_proxy)
        Util.set_env('https_proxy', https_proxy)

    @staticmethod
    def get_caller_name():
        return inspect.stack()[1][3]

    @staticmethod
    def strace_function(frame, event, arg, indent=[0]):
        file_path = frame.f_code.co_filename
        function_name = frame.f_code.co_name
        file_name = file_path.split('/')[-1]
        if not file_path[:4] == '/usr' and not file_path == '<string>':
            if event == 'call':
                indent[0] += 2
                Util.strace('-' * indent[0] + '> call %s:%s' % (file_name, function_name))
            elif event == 'return':
                Util.strace('<' + '-' * indent[0] + ' exit %s:%s' % (file_name, function_name))
                indent[0] -= 2
        return Util.strace_function

    @staticmethod
    # Get the dir of symbolic link, for example: /workspace/project/chromium instead of /workspace/project/gyagp/share/python
    def get_symbolic_link_dir():
        if sys.argv[0][0] == '/':  # Absolute path
            script_path = sys.argv[0]
        else:
            script_path = os.getcwd() + '/' + sys.argv[0]
        return os.path.split(script_path)[0]

    @staticmethod
    def union_list(a, b):
        return list(set(a).union(set(b)))

    @staticmethod
    def intersect_list(a, b):
        return list(set(a).intersection(set(b)))

    @staticmethod
    def diff_list(a, b):
        return list(set(a).difference(set(b)))

    @staticmethod
    def send_email(sender, to, subject, content, type='plain'):
        if isinstance(to, list):
            to = ','.join(to)

        to_list = to.split(',')
        msg = MIMEMultipart('alternative')
        msg['From'] = sender
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(content, type))

        try:
            smtp = smtplib.SMTP('localhost')
            smtp.sendmail(sender, to_list, msg.as_string())
            Util.info('Email was sent successfully')
        except Exception as e:
            Util.error('Failed to send mail: %s' % e)
        finally:
            smtp.quit()

    @staticmethod
    def get_working_dir_commit_info(src_dir):
        Util.chdir(src_dir)
        cmd = 'git show -s --format=%ai -1'
        result = Util.execute(cmd, return_out=True)
        date = result[1].split(' ')[0].replace('-', '')
        return [date]

    @staticmethod
    def get_mesa_build_pattern(rev='latest'):
        if rev == 'latest':
            rev = '(.*)'
        return r'mesa-master-release-\d{8}-%s-[a-z0-9]{40}(?<!tar.gz)$' % rev

    @staticmethod
    def get_rev_dir(parent_dir, type, rev):
        if type == 'mesa':
            rev_pattern = Util.get_mesa_build_pattern(rev)
        elif type == 'chrome':
            rev_pattern = Util.CHROME_BUILD_PATTERN

        if rev == 'latest':
            rev = -1
            rev_dir = ''
            files = os.listdir(parent_dir)
            for file in files:
                match = re.search(rev_pattern, file)
                if match:
                    tmp_rev = int(match.group(1))
                    if tmp_rev > rev:
                        rev_dir = file
                        rev = tmp_rev

            return (rev_dir, rev)
        else:
            files = os.listdir(parent_dir)
            for file in files:
                match = re.match(rev_pattern, file)
                if match:
                    rev_dir = file
                    return (rev_dir, rev)
            else:
                Util.error('Could not find mesa build %s' % rev)

    @staticmethod
    def get_quotation():
        if Util.HOST_OS == 'windows':
            quotation = '\"'
        else:
            quotation = '\''

        return quotation

    @staticmethod
    def use_slash(s):
        return s.replace('\\', '/')

    @staticmethod
    def use_backslash(s):
        return s.replace('/', '\\')

    MAX_REV = 9999999
    CHROME_BUILD_PATTERN = r'(\d{6}).zip'
    HOST_OS = platform.system().lower()
    HOST_OS_ID = ''
    HOST_OS_RELEASE = '0.0'
    if HOST_OS == 'linux':
        result = subprocess.check_output(['cat', '/etc/lsb-release']).decode('utf-8')
        if re.search('CHROMEOS', result[1]):
            HOST_OS = 'chromeos'

    if HOST_OS == 'chromeos':
        HOST_OS_RELEASE = platform.platform()
    elif HOST_OS == 'darwin':
        HOST_OS_RELEASE = platform.mac_ver()[0]
    elif HOST_OS == 'linux':
        dist = platform.dist()
        HOST_OS_ID = dist[0].lower()
        HOST_OS_RELEASE = dist[1]
    elif HOST_OS == 'windows':
        HOST_OS_RELEASE = platform.version()

    HOST_NAME = socket.gethostname()
    if HOST_OS == 'windows':
        USER_NAME = os.getenv('USERNAME')
    else:
        USER_NAME = os.getenv('USER')
    CPU_COUNT = multiprocessing.cpu_count()

    if HOST_OS == 'windows':
        PROJECT_DIR = 'd:/workspace/project/readonly'
    else:
        PROJECT_DIR = '/workspace/project/readonly'

    if HOST_OS == 'windows':
        APPDATA_DIR = use_slash.__func__(os.getenv('APPDATA'))
        PROGRAMFILES_DIR = use_slash.__func__(os.getenv('PROGRAMFILES'))
        PROGRAMFILESX86_DIR = use_slash.__func__(os.getenv('PROGRAMFILES(X86)'))

    if HOST_OS == 'windows':
        ENV_SPLITTER = ';'
        EXEC_SUFFIX = '.exe'
    elif HOST_OS in ['linux', 'darwin', 'chromeos']:
        ENV_SPLITTER = ':'
        EXEC_SUFFIX = ''


class Timer():
    def __init__(self, microsecond=False):
        self.timer = [0, 0]
        if microsecond:
            self.timer[0] = datetime.datetime.now()
        else:
            self.timer[0] = datetime.datetime.now().replace(microsecond=0)

    def stop(self, microsecond=False):
        if microsecond:
            self.timer[1] = datetime.datetime.now()
        else:
            self.timer[1] = datetime.datetime.now().replace(microsecond=0)

        return self.timer[1] - self.timer[0]

class ScriptRepo:
    tmp_dir = Util.get_dir(__file__)
    while not os.path.exists(tmp_dir + '/.git') or os.path.basename(tmp_dir) == 'util':
        tmp_dir = Util.get_dir(tmp_dir)
    ROOT_DIR = Util.use_slash(tmp_dir)
    TOOL_DIR = '%s/tool' % ROOT_DIR
    IGNORE_DIR = '%s/ignore' % ROOT_DIR
    IGNORE_LOG_DIR = '%s/log' % IGNORE_DIR
    IGNORE_TIMESTAMP_DIR = '%s/timestamp' % IGNORE_DIR
    IGNORE_CHROMIUM_DIR = '%s/chromium' % IGNORE_DIR
    IGNORE_CHROMIUM_SELFBUILT_DIR = '%s/selfbuilt' % IGNORE_CHROMIUM_DIR
    IGNORE_CHROMIUM_DOWNLOAD_DIR = '%s/download' % IGNORE_CHROMIUM_DIR
    IGNORE_CHROMIUM_BOTO_FILE = '%s/boto.conf' % IGNORE_CHROMIUM_DIR

class Program():
    def __init__(self, parser):
        parser.add_argument('--root-dir', dest='root_dir', help='set root directory')
        parser.add_argument('--timestamp', dest='timestamp', help='timestamp')
        parser.add_argument('--log-file', dest='log_file', help='log file')
        parser.add_argument('--fixed-timestamp', dest='fixed_timestamp', help='fixed timestamp for test sake. We may run multiple tests and results are in same dir', action='store_true')
        parser.add_argument('--proxy', dest='proxy', help='proxy')

        args = parser.parse_args()

        if args.root_dir:
            root_dir = args.root_dir
        elif os.path.islink(sys.argv[0]):
            root_dir = Util.get_symbolic_link_dir()
        else:
            root_dir = os.path.abspath(os.getcwd())

        if args.timestamp:
            timestamp = args.timestamp
        elif args.fixed_timestamp:
            timestamp = Util.get_datetime(format='%Y%m%d')
        else:
            timestamp = Util.get_datetime()

        if args.log_file:
            log_file = args.log_file
        else:
            script_name = os.path.basename(sys.argv[0]).replace('.py', '')
            log_file = ScriptRepo.IGNORE_LOG_DIR + '/' + script_name + '-' + timestamp + '.log'
        Util.info('Log file: %s' % log_file)

        if args.proxy:
            proxy_parts = args.proxy.split(':')
            proxy_address = proxy_parts[0]
            proxy_port = proxy_parts[1]
        else:
            proxy_address = ''
            proxy_port = ''

        Util.ensure_dir(root_dir)
        Util.chdir(root_dir)
        Util.ensure_dir(ScriptRepo.IGNORE_TIMESTAMP_DIR)
        Util.ensure_dir(ScriptRepo.IGNORE_LOG_DIR)

        self.args = args
        self.root_dir = root_dir
        self.timestamp = timestamp
        self.log_file = log_file
        self.proxy_address = proxy_address
        self.proxy_port = proxy_port

    def execute(self, cmd, show_cmd=True, exit_on_error=True, return_out=False, show_duration=False, dryrun=False):
        return Util.execute(cmd=cmd, show_cmd=show_cmd, exit_on_error=exit_on_error, return_out=return_out, show_duration=show_duration, dryrun=dryrun, log_file=self.log_file)

    def execute_gclient(self, cmd_type, job_count=0, extra_cmd='', verbose=False):
        self._set_boto()
        cmd = 'gclient ' + cmd_type
        if extra_cmd:
            cmd += ' ' + extra_cmd
        if cmd_type == 'sync':
            cmd += ' -n -D -R --break_repo_locks --delete_unversioned_trees'

        if not job_count:
            job_count = Util.CPU_COUNT
        cmd += ' -j%s' % job_count

        if verbose:
            cmd += ' -v'

        if Util.HOST_OS == 'windows':
            depot_tools_path = 'd:/workspace/project/readonly/depot_tools'
        else:
            depot_tools_path = '/workspace/project/readonly/depot_tools'

        if not Util.has_depot_tools_in_path() and os.path.exists(depot_tools_path):
            Util.prepend_path(depot_tools_path)

        result = Util.execute(cmd=cmd)

        if not Util.has_depot_tools_in_path() and os.path.exists(depot_tools_path):
            Util.remove_path(depot_tools_path)

        return result

    def _set_boto(self):
        if not self.args.proxy:
            return

        boto_file = ScriptRepo.IGNORE_CHROMIUM_BOTO_FILE
        if not os.path.exists(boto_file):
            lines = [
                '[Boto]',
                'proxy = %s' % self.program.proxy_address,
                'proxy_port = %s' % self.program.proxy_port,
                'proxy_rdns = True',
            ]
            Util.write_file(boto_file, lines)

        Util.set_env('NO_AUTH_BOTO_CONFIG', boto_file)

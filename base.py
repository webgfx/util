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
import zipfile

try:
    import urllib2
except ImportError:
    pass

try:
    import win32com.client # install pywin32
except ImportError:
    pass

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions
    from selenium.webdriver.support.select import Select
    from selenium.webdriver.support.ui import WebDriverWait

except ImportError:
    pass

def retry(ExceptionToCheck, tries=4, delay=3, backoff=2, logger=None):
    """Retry calling the decorated function using an exponential backoff.

    http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param ExceptionToCheck: the exception to check. may be a tuple of
        exceptions to check
    :type ExceptionToCheck: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
        each retry
    :type backoff: int
    :param logger: logger to use. If None, print
    :type logger: logging.Logger instance
    """
    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck as e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logger.warning(msg)
                    else:
                        print(msg)
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry

class Util:
    @staticmethod
    def execute(cmd, show_cmd=True, exit_on_error=True, return_out=False, show_duration=False, dryrun=False, log_file=''):
        orig_cmd = cmd
        if show_cmd:
            Util.cmd(orig_cmd)

        if Util.HOST_OS == Util.WINDOWS:
            cmd = '%s 2>&1' % cmd
        else:
            cmd = 'bash -o pipefail -c "%s 2>&1' % cmd
        if log_file:
            cmd += ' | tee -a %s' % log_file
        if not Util.HOST_OS == Util.WINDOWS:
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
    def not_implemented():
        Util.error('not_implemented() at line %s' % inspect.stack()[1][2])

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
        else:
            del os.environ[env]

    # get seconds since 1970-01-01
    @staticmethod
    def get_epoch_second():
        return int(time.time())

    @staticmethod
    def has_recent_change(file_path, interval=24 * 3600):
        if Util.get_epoch_second() - os.path.getmtime(file_path) < interval:
            return True
        else:
            return False

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
    def del_filetype_in_dir(dir_path, filetype):
        for root, dirs, files in os.walk(dir_path):
            for name in files:
                if (name.endswith('.%s' % filetype)):
                    os.remove(os.path.join(root, name))

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
    def clear_proxy():
        Util.set_env('http_proxy', '')
        Util.set_env('https_proxy', '')

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
    def get_rev_dir(dir, type, rev):
        if type == 'mesa':
            rev_pattern = Util.get_mesa_build_pattern(rev)
        elif type == 'chrome':
            rev_pattern = Util.CHROME_BUILD_PATTERN

        if rev == 'latest':
            rev = -1
            rev_dir = ''
            files = os.listdir(dir)
            for file in files:
                match = re.search(rev_pattern, file)
                if match:
                    tmp_rev = int(match.group(1))
                    if tmp_rev > rev:
                        rev_dir = file
                        rev = tmp_rev

            return (rev_dir, rev)
        else:
            files = os.listdir(dir)
            for file in files:
                match = re.match(rev_pattern, file)
                if match:
                    rev_dir = file
                    return (rev_dir, rev)
            else:
                Util.error('Could not find mesa build %s' % rev)

    @staticmethod
    def set_mesa(dir, rev, type='iris'):
        if rev == 'system':
            Util.ensure_pkg('mesa-vulkan-drivers')
            Util.info('Use system Mesa')
        else:
            (rev_dir, _) = Util.get_rev_dir(dir, 'mesa', rev)
            mesa_dir = '%s/%s' % (dir, rev_dir)
            Util.set_env('LD_LIBRARY_PATH', '%s/lib' % mesa_dir)
            Util.set_env('LIBGL_DRIVERS_PATH', '%s/lib/dri' % mesa_dir)
            Util.set_env('VK_ICD_FILENAMES', '%s/share/vulkan/icd.d/intel_icd.x86_64.json' % mesa_dir)

            if type == 'iris':
                Util.set_env('MESA_LOADER_DRIVER_OVERRIDE', 'iris')
            else:
                Util.set_env('MESA_LOADER_DRIVER_OVERRIDE', 'i965')

            Util.info('Use mesa at %s' % mesa_dir)

    @staticmethod
    def get_quotation():
        if Util.HOST_OS == Util.WINDOWS:
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

    @staticmethod
    @retry(Exception, tries=5, delay=3, backoff=2)
    def urlopen_with_retry(url):
        return urllib2.urlopen(url)

    @staticmethod
    def get_relative_out_dir(target_arch, target_os, symbol_level=0, no_component_build=False, dcheck=False):
        relative_out_dir = 'out-%s-%s' % (target_arch, target_os)
        relative_out_dir += '-symbol%s' % symbol_level

        if no_component_build:
            relative_out_dir += '-nocomponent'
        else:
            relative_out_dir += '-component'

        if dcheck:
            relative_out_dir += '-dcheck'
        else:
            relative_out_dir += '-nodcheck'

        return relative_out_dir

    @staticmethod
    def parse_git_line(lines, index, tmp_rev, tmp_hash, tmp_author, tmp_date, tmp_subject, tmp_insertion, tmp_deletion, tmp_is_roll):
        line = lines[index]
        strip_line = line.strip()
        # hash
        match = re.match(Util.COMMIT_STR, line)
        if match:
            tmp_hash = match.group(1)

        # author
        match = re.match('Author:', lines[index])
        if match:
            match = re.search('<(.*@.*)@.*>', line)
            if match:
                tmp_author = match.group(1)
            else:
                match = re.search(r'(\S+@\S+)', line)
                if match:
                    tmp_author = match.group(1)
                    tmp_author = tmp_author.lstrip('<')
                    tmp_author = tmp_author.rstrip('>')
                else:
                    tmp_author = line.rstrip('\n').replace('Author:', '').strip()
                    Util.warning('The author %s is in abnormal format' % tmp_author)

        # date & subject
        match = re.match('Date:(.*)', line)
        if match:
            tmp_date = match.group(1).strip()
            index += 2
            tmp_subject = lines[index].strip()
            match = re.match(r'Roll (.*) ([a-zA-Z0-9]+)..([a-zA-Z0-9]+) \((\d+) commits\)', tmp_subject)
            if match and match.group(1) != 'src-internal':
                tmp_is_roll = True

        # rev
        # < r291561, use below format
        # example: git-svn-id: svn://svn.chromium.org/chrome/trunk/src@291560 0039d316-1c4b-4281-b951-d872f2087c98
        match = re.match('git-svn-id: svn://svn.chromium.org/chrome/trunk/src@(.*) .*', strip_line)
        if match:
            tmp_rev = int(match.group(1))

        # >= r291561, use below format
        # example: Cr-Commit-Position: refs/heads/master@{#349370}
        match = re.match('Cr-Commit-Position: refs/heads/master@{#(.*)}', strip_line)
        if match:
            tmp_rev = int(match.group(1))

        if re.match(r'(\d+) files? changed', strip_line):
            match = re.search(r'(\d+) insertion(s)*\(\+\)', strip_line)
            if match:
                tmp_insertion = int(match.group(1))
            else:
                tmp_insertion = 0

            match = re.search(r'(\d+) deletion(s)*\(-\)', strip_line)
            if match:
                tmp_deletion = int(match.group(1))
            else:
                tmp_deletion = 0

        return (tmp_rev, tmp_hash, tmp_author, tmp_date, tmp_subject, tmp_insertion, tmp_deletion, tmp_is_roll)

    @staticmethod
    def get_webdriver(browser_name, browser_path='', browser_options='', webdriver_path='', debug=False, target_os=''):
        if not target_os:
            target_os = Util.HOST_OS
        # options
        options = []
        if 'chrome' in browser_name:
            # --start-maximized doesn't work on darwin
            if target_os in [Util.DARWIN]:
                options.append('--start-fullscreen')
            elif target_os in [Util.WINDOWS, Util.LINUX]:
                options.append('--start-maximized')
            if target_os != Util.CHROMEOS:
                options.extend(['--disk-cache-dir=/dev/null', '--disk-cache-size=1', '--user-data-dir=%s' % (ScriptRepo.USER_DATA_DIR)])
            if debug:
                service_args = ["--verbose", "--log-path=%s/chromedriver.log" % dir_share_ignore_log]
            else:
                service_args = []
        if browser_options:
            options.extend(browser_options.split(','))

        # browser_path
        if not browser_path:
            out_dir = Util.get_relative_out_dir('x86_64', Util.HOST_OS)
            if target_os == Util.CHROMEOS:
                browser_path = '/opt/google/chrome/chrome'
            elif target_os == Util.DARWIN:
                if browser_name == 'chrome':
                    browser_path = Util.PROJECT_CHROME_SRC_DIR + '/%s/Release/Chromium.app/Contents/MacOS/Chromium' % out_dir
                elif browser_name == 'chrome_canary':
                    browser_path = '/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary'
            elif target_os == Util.LINUX:
                if browser_name == 'chrome':
                    browser_path = Util.PROJECT_CHROME_SRC_DIR + '/%s/Release/chrome' % out_dir
                elif browser_name == 'chrome_stable':
                    browser_path = '/usr/bin/google-chrome-stable'
                elif browser_name == 'chrome_canary':
                    browser_path = '/usr/bin/google-chrome-unstable'
            elif target_os == Util.WINDOWS:
                if browser_name == 'chrome':
                    browser_path = Util.PROJECT_CHROME_SRC_DIR + '/%s/Release/chrome.exe' % out_dir
                elif browser_name == 'chrome_stable':
                    browser_path = '%s/../Local/Google/Chrome/Application/chrome.exe' % Util.APPDATA_DIR
                elif browser_name == 'chrome_beta':
                    browser_path = '%s/Google/Chrome Beta/Application/chrome.exe' % Util.PROGRAMFILESX86_DIR
                elif browser_name == 'chrome_dev':
                    browser_path = '%s/Google/Chrome Dev/Application/chrome.exe' % Util.PROGRAMFILESX86_DIR
                elif browser_name == 'chrome_canary':
                    browser_path = '%s/../Local/Google/Chrome SxS/Application/chrome.exe' % Util.APPDATA_DIR
                elif browser_name == 'firefox_nightly':
                    browser_path = '%s/Nightly/firefox.exe' % Util.PROGRAMFILES_DIR
                elif browser_name == 'edge':
                    browser_path = 'C:/windows/systemapps/Microsoft.MicrosoftEdge_8wekyb3d8bbwe/MicrosoftEdge.exe'
        # webdriver_path
        if not webdriver_path:
            if target_os == Util.CHROMEOS:
                webdriver_path = '/user/local/chromedriver/chromedriver'
            elif browser_name == 'chrome':
                if Util.HOST_OS == Util.DARWIN:
                    chrome_dir = browser_path.replace('/Chromium.app/Contents/MacOS/Chromium', '')
                else:
                    chrome_dir = os.path.dirname(os.path.realpath(browser_path))
                webdriver_path = chrome_dir + '/chromedriver'
                webdriver_path = webdriver_path.replace('\\', '/')
                if Util.HOST_OS == Util.WINDOWS:
                    webdriver_path += '.exe'
            elif target_os in [Util.DARWIN, Util.LINUX, Util.WINDOWS]:
                if 'chrome' in browser_name:
                    webdriver_path = ScriptRepo.CHROMEDRIVER_PATH
                elif 'firefox' in browser_name:
                    webdriver_path = Util.FIREFOXDRIVER_PATH
                elif 'edge' in browser_name:
                    webdriver_path = Util.EDGEDRIVER_PATH
        # driver
        if target_os == Util.CHROMEOS:
            import chromeoswebdriver
            driver = chromeoswebdriver.chromedriver(extra_chrome_flags=options).driver
        elif target_os in [Util.DARWIN, Util.LINUX, Util.WINDOWS]:
            if 'chrome' in browser_name:
                chrome_options = webdriver.ChromeOptions()
                for option in options:
                    chrome_options.add_argument(option)
                chrome_options.binary_location = browser_path
                if debug:
                    service_args = ["--verbose", "--log-path=%s/chromedriver.log" % dir_share_ignore_log]
                else:
                    service_args = []
                driver = webdriver.Chrome(executable_path=webdriver_path, chrome_options=chrome_options, service_args=service_args)
            elif 'firefox' in browser_name:
                from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
                capabilities = DesiredCapabilities.FIREFOX
                capabilities['marionette'] = True
                # capabilities['binary'] = browser_path
                driver = webdriver.Firefox(capabilities=capabilities, executable_path=webdriver_path)
            elif 'edge' in browser_name:
                driver = webdriver.Edge(webdriver_path)

        if not browser_path:
            Util.error('Could not find module at %s' % browser_path)
        else:
            Util.info('Use module at %s' % browser_path)
        if not webdriver_path:
            Util.error('Could not find webdriver at %s' % webdriver_path)
        else:
            Util.info('Use webdriver at %s' % webdriver_path)
        if not driver:
            Util.error('Could not get webdriver')

        return driver

    @staticmethod
    def backup_gn_target(repo_dir, out_dir, backup_dir, targets, target_dict={}, need_symbol=False, target_os=''):
        if os.path.exists(backup_dir):
            Util.info('Backup folder "%s" alreadys exists' % backup_dir)
            return
            #os.rename(backup_dir, '%s-%s' % (backup_dir, Util.get_datetime()))

        Util.chdir(repo_dir)
        for key, value in target_dict.items():
            if key in targets:
                targets[targets.index(key)] = value

        tmp_files = []
        for target in targets:
            target_files = Util.execute('gn desc %s %s runtime_deps' % (out_dir, target), return_out=True)[1].rstrip('\n').split('\n')
            tmp_files = Util.union_list(tmp_files, target_files)

        exclude_files = ['gen/', '../../.vpython']
        src_files = []
        for tmp_file in tmp_files:
            if not need_symbol and tmp_file.endswith('.pdb'):
                continue

            if tmp_file.startswith('./'):
                tmp_file = tmp_file[2:]

            if target_os == Util.CHROMEOS and not tmp_file.startswith('../../'):
                continue

            for exclude_file in exclude_files:
                if tmp_file.startswith(exclude_file):
                    break
            else:
                src_files.append(tmp_file)

        for src_file in src_files:
            src_file = '%s/%s' % (out_dir, src_file)
            dst_dir = '%s/%s' % (backup_dir, src_file)
            Util.ensure_dir(os.path.dirname(dst_dir))
            if os.path.isdir(src_file):
                dst_dir = os.path.dirname(os.path.dirname(dst_dir))
            Util.execute('cp -rf %s %s' % (src_file, dst_dir), show_cmd=True)

            # permission denied
            #shutil.copyfile(file, dst_dir)

    @staticmethod
    def get_md5(path, verbose=False):
        if verbose:
            info('Calculating md5 of %s' % path)

        if Util.need_sudo(path):
            name = os.path.basename(path)
            Util.execute('sudo cp %s /tmp' % path, show_cmd=False)
            Util.execute('sudo chmod +r /tmp/%s' % name, show_cmd=False)
            md5 = hashlib.md5(open('/tmp/%s' % name, 'rb').read()).hexdigest()
            Util.execute('sudo rm /tmp/%s' % name, show_cmd=False)
        else:
            md5 = hashlib.md5(open(path, 'rb').read()).hexdigest()
        return md5

    @staticmethod
    def has_path(path):
        if Util.need_sudo(path):
            result = Util.execute('sudo ls %s' % path, show_cmd=False, exit_on_error=False)
            if result[0] == 0:
                return True
            else:
                return False
        else:
            return os.path.exists(path)

    @staticmethod
    def has_link(path):
        if Util.need_sudo(path) or Util.HOST_OS == Util.WINDOWS:
            cmd = 'file "%s"' % path
            if Util.need_sudo(path):
                cmd = 'sudo ' + cmd
            result = Util.execute(cmd, show_cmd=False, return_out=True)
            if re.search('symbolic link to', result[1]):
                return True
            else:
                return False
        else:
            return os.path.islink(path)

    @staticmethod
    def use_drive(s):
        m = re.match('/(.)/', s)
        if m:
            drive = m.group(1)
            s = s.replace('/%s/' % drive, '%s:/' % drive.capitalize())
        return s

    # get the real file from symbolic link
    @staticmethod
    def get_link(path):
        if not Util.has_link(path):
            error('%s is not a symbolic link' % path)

        if Util.need_sudo(path) or Util.HOST_OS == Util.WINDOWS:
            cmd = 'file "%s"' % path
            if Util.need_sudo(path):
                cmd = 'sudo ' + cmd
            result = Util.execute(cmd, show_cmd=False, return_out=True)
            match = re.search('symbolic link to (.*)', result[1])
            link = match.group(1).strip()
            if Util.HOST_OS == Util.WINDOWS:
                link = Util.use_drive(link)
            return link
        else:
            return os.readlink(path)  # pylint: disable=E1101

    @staticmethod
    def need_sudo(path):
        if re.match('/var', path):
            return True
        elif re.match('/etc/apache2', path):
            return True
        else:
            return False

    # return True if there is a real update
    # is_sylk: If true, just copy as a symbolic link
    # dir_xxx means directory
    # name_xxx means file name
    # path_xxx means full path of file
    # need_bk means if it needs .bk file
    @staticmethod
    def copy_file(src_dir, src_name, dest_dir, dest_name='', is_sylk=False, need_bk=True):
        if not os.path.exists(dest_dir):
            # we do not warn here as it's a normal case
            # warning(dest_dir + ' does not exist')
            return False

        if not dest_name:
            dest_name = src_name
        path_dest = dest_dir + '/' + dest_name
        path_dest_bk = path_dest + '.bk'

        # hack the src_name to support machine specific config
        # For example, wp-27-hostapd.conf
        # src_name is changed here, so we can't put this before path_dest definition
        if os.path.exists(src_dir + '/' + Util.HOST_NAME + '-' + src_name):
            src_name = Util.HOST_NAME + '-' + src_name
        path_src = src_dir + '/' + src_name
        if not os.path.exists(path_src):
            Util.warning(path_src + ' does not exist')
            return False

        need_copy = False
        need_bk_tmp = False
        has_update = False

        if not Util.has_path(path_dest) or Util.has_link(path_dest) != is_sylk:
            need_copy = True
            need_bk_tmp = True
            has_update = True
        elif is_sylk:  # both are symbolic link
            if Util.get_link(path_dest) != path_src:
                need_copy = True
                need_bk_tmp = True
                has_update = True
            else:  # same link
                if not Util.has_path(path_dest_bk):
                    need_bk_tmp = True
                    has_update = True
                else:
                    if Util.get_md5(path_dest) != Util.get_md5(path_dest_bk):
                        need_bk_tmp = True
                        has_update = True
        else:  # both are real files
            if not os.path.exists(path_dest_bk):
                need_bk_tmp = True

            if Util.get_md5(path_dest) != Util.get_md5(path_src):
                need_copy = True
                need_bk_tmp = True
                has_update = True
        # print need_copy, need_bk_tmp, has_update

        if re.search('chroot/sbin', dest_dir):
            need_sudo = True
        elif re.search(Util.HOME_DIR, dest_dir) or re.search(Util.WORKSPACE_DIR, dest_dir):
            need_sudo = False
        else:
            need_sudo = True

        if need_bk_tmp and need_bk:
            cmd = 'rm -f "%s"' % path_dest_bk
            if need_sudo:
                cmd = 'sudo ' + cmd
            Util.execute(cmd, show_cmd=False, exit_on_error=False)
            cmd = 'cp -f "%s" "%s"' % (path_dest, path_dest_bk)
            if need_sudo:
                cmd = 'sudo ' + cmd
            Util.execute(cmd, show_cmd=False, exit_on_error=False)

        if need_copy:
            cmd = 'rm "%s"' % path_dest
            if need_sudo:
                cmd = 'sudo ' + cmd
            Util.execute(cmd, show_cmd=False, exit_on_error=False)

            if is_sylk:
                if Util.HOST_OS == Util.WINDOWS:
                    cmd = 'mklink "%s" "%s"' % (path_dest, path_src)
                else:
                    cmd = 'ln -s ' + path_src + ' ' + path_dest
            else:
                cmd = 'cp -rf ' + path_src + ' ' + path_dest
            if need_sudo:
                cmd = 'sudo ' + cmd
            result = Util.execute(cmd, show_cmd=False)
            if result[0]:
                error('Failed to execute %s. You may need to run cmd with administrator priviledge' % cmd)

        return has_update

    MYSQL_SERVER = 'wp-27'
    WINDOWS = 'windows'
    LINUX = 'linux'
    DARWIN = 'darwin'
    CHROMEOS = 'chromeos'
    ANDROID = 'android'
    MAX_REV = 9999999
    CHROME_BUILD_PATTERN = r'(\d{6})'
    COMMIT_STR = 'commit (.*)'
    HOST_OS = platform.system().lower()
    HOST_OS_ID = ''
    HOST_OS_RELEASE = '0.0'
    if HOST_OS == LINUX:
        result = subprocess.check_output(['cat', '/etc/lsb-release']).decode('utf-8')
        if re.search(CHROMEOS, result[1]):
            HOST_OS = CHROMEOS

    if HOST_OS == CHROMEOS:
        HOST_OS_RELEASE = platform.platform()
    elif HOST_OS == DARWIN:
        HOST_OS_RELEASE = platform.mac_ver()[0]
    elif HOST_OS == WINDOWS:
        HOST_OS_RELEASE = platform.version()

    HOST_NAME = socket.gethostname()
    if HOST_OS == WINDOWS:
        USER_NAME = os.getenv('USERNAME')
    else:
        USER_NAME = os.getenv('USER')
    CPU_COUNT = multiprocessing.cpu_count()

    if HOST_OS == WINDOWS:
        WORKSPACE_DIR = 'd:/workspace'
    else:
        WORKSPACE_DIR = '/workspace'
    BACKUP_DIR = '%s/backup' % WORKSPACE_DIR
    PROJECT_DIR = '%s/project' % WORKSPACE_DIR
    PROJECT_ANGLE_DIR = '%s/angle' % PROJECT_DIR
    PROJECT_CHROME_DIR = '%s/chromium' % PROJECT_DIR
    PROJECT_CHROME_SRC_DIR = '%s/src' % PROJECT_CHROME_DIR
    PROJECT_DAWN_DIR = '%s/dawn' % PROJECT_DIR
    PROJECT_DEPOT_TOOLS = '%s/depot_tools' % PROJECT_DIR
    PROJECT_MESA_DIR = '%s/mesa' % PROJECT_DIR
    PROJECT_MESA_BACKUP_DIR = '%s/backup' % PROJECT_MESA_DIR
    PROJECT_SKIA_DIR = '%s/skia' % PROJECT_DIR
    PROJECT_TFJS_DIR = '%s/tfjs' % PROJECT_DIR
    PROJECT_TOOLKIT_DIR = '%s/toolkit' % PROJECT_DIR
    PROJECT_V8_DIR = '%s/v8' % PROJECT_DIR
    PROJECT_WASM_DIR = '%s/wasm' % PROJECT_DIR
    PROJECT_WEBGL_DIR = '%s/WebGL' % PROJECT_DIR
    PROJECT_WEBGPUCTS_DIR = '%s/webgpucts' % PROJECT_DIR
    PROJECT_WEBGPUSPEC_DIR = '%s/webgpuspec' % PROJECT_DIR
    PROJECT_WEBBENCH_DIR = '%s/webbench' % PROJECT_DIR
    PROJECT_WORK_DIR = '%s/work' % PROJECT_DIR
    PROJECT_WPT_DIR = '%s/web-platform-tests' % PROJECT_DIR

    HOME_DIR = use_slash.__func__(expanduser("~"))

    if HOST_OS == WINDOWS:
        APPDATA_DIR = use_slash.__func__(os.getenv('APPDATA'))
        PROGRAMFILES_DIR = use_slash.__func__(os.getenv('PROGRAMFILES'))
        PROGRAMFILESX86_DIR = use_slash.__func__(os.getenv('PROGRAMFILES(X86)'))

    if HOST_OS == WINDOWS:
        ENV_SPLITTER = ';'
        EXEC_SUFFIX = '.exe'
    elif HOST_OS in [LINUX, DARWIN, CHROMEOS]:
        ENV_SPLITTER = ':'
        EXEC_SUFFIX = ''

    INTERNAL_WEBSERVER = 'http://wp-27'
    INTERNAL_WEBSERVER_WEBBENCH = '%s/%s/webbench' % (INTERNAL_WEBSERVER, PROJECT_DIR)

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
    UTIL_DIR = '%s/util' % ROOT_DIR
    TOOL_DIR = '%s/tool' % UTIL_DIR
    if Util.HOST_OS == Util.WINDOWS:
        Util.prepend_path(TOOL_DIR)

    IGNORE_DIR = '%s/ignore' % ROOT_DIR
    IGNORE_LOG_DIR = '%s/log' % IGNORE_DIR
    IGNORE_TIMESTAMP_DIR = '%s/timestamp' % IGNORE_DIR
    IGNORE_CHROMIUM_DIR = '%s/chromium' % IGNORE_DIR
    IGNORE_CHROMIUM_SELFBUILT_DIR = '%s/selfbuilt' % IGNORE_CHROMIUM_DIR
    IGNORE_CHROMIUM_DOWNLOAD_DIR = '%s/download' % IGNORE_CHROMIUM_DIR
    IGNORE_CHROMIUM_BOTO_FILE = '%s/boto.conf' % IGNORE_CHROMIUM_DIR
    IGNORE_WEBMARK_DIR = '%s/webmark' % IGNORE_DIR
    IGNORE_WEBMARK_RESULT_DIR = '%s/result' % IGNORE_WEBMARK_DIR

    USER_DATA_DIR = '%s/user-data-dir-%s' % (IGNORE_CHROMIUM_DIR, Util.USER_NAME)
    W3C_DIR = '%s/w3c' % ROOT_DIR
    CONTRIB_DIR = '%s/contrib' % ROOT_DIR
    CHROMEDRIVER_PATH = '%s/webdriver/%s/chromedriver%s' % (TOOL_DIR, Util.HOST_OS, Util.EXEC_SUFFIX)

class Program():
    def __init__(self, parser):
        parser.add_argument('--root-dir', dest='root_dir', help='set root directory')
        parser.add_argument('--timestamp', dest='timestamp', help='timestamp')
        parser.add_argument('--log-file', dest='log_file', help='log file')
        parser.add_argument('--fixed-timestamp', dest='fixed_timestamp', help='fixed timestamp for test sake. We may run multiple tests and results are in same dir', action='store_true')
        parser.add_argument('--proxy', dest='proxy', help='proxy')
        parser.add_argument('--target-arch', dest='target_arch', help='target arch', choices=['x86', 'arm', 'x86_64', 'arm64'], default='default')
        parser.add_argument('--target-os', dest='target_os', help='target os, choices can be android, linux, chromeos, windows, darwin', default='default')


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
        if args.target_arch == 'default':
            self.target_arch = 'x86_64'
        if args.target_os == 'default':
            self.target_os = Util.HOST_OS

    def execute(self, cmd, show_cmd=True, exit_on_error=True, return_out=False, show_duration=False, dryrun=False):
        return Util.execute(cmd=cmd, show_cmd=show_cmd, exit_on_error=exit_on_error, return_out=return_out, show_duration=show_duration, dryrun=dryrun, log_file=self.log_file)

    def execute_gclient(self, cmd_type, job_count=0, extra_cmd='', verbose=False):
        self._set_boto()
        cmd = 'gclient ' + cmd_type
        if extra_cmd:
            cmd += ' ' + extra_cmd
        if cmd_type == 'sync':
            cmd += ' -n -D -R --delete_unversioned_trees'

        if not job_count:
            job_count = Util.CPU_COUNT
        cmd += ' -j%s' % job_count

        if verbose:
            cmd += ' -v'

        if not Util.has_depot_tools_in_path() and os.path.exists(Util.PROJECT_DEPOT_TOOLS):
            Util.prepend_path(Util.PROJECT_DEPOT_TOOLS)

        result = Util.execute(cmd=cmd)

        if not Util.has_depot_tools_in_path() and os.path.exists(Util.PROJECT_DEPOT_TOOLS):
            Util.remove_path(Util.PROJECT_DEPOT_TOOLS)

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

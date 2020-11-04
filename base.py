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
            if log_file:
                fail_file = Util.format_slash(ScriptRepo.IGNORE_FAIL_FILE)
                Util.ensure_file(fail_file)
                cmd = '(%s && del %s) 2>&1 | tee -a %s' % (cmd, fail_file, log_file)
        else:
            cmd = 'bash -o pipefail -c "%s' % cmd
            if log_file:
                cmd += ' 2>&1 | tee -a %s' % log_file
            cmd += '; (exit ${PIPESTATUS})"'

        if show_duration:
            timer = Timer()

        if dryrun:
            ret = 0
            out = ''
        else:
            if return_out:
                process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                (out, err) = process.communicate()
                ret = process.returncode
                out = (out + err).decode('utf-8').rstrip('\n')
            else:
                ret = os.system(cmd)
                out = ''

            if log_file and Util.HOST_OS == Util.WINDOWS:
                if os.path.exists(fail_file):
                    #Util.ensure_nofile(fail_file)
                    ret = 1
                else:
                    ret = 0

        result = [ret, out]

        if show_duration:
            Util.info('%s was spent to execute command "%s" in function "%s"' % (timer.stop(), orig_cmd, inspect.stack()[1][3]))

        if ret:
            if exit_on_error:
                Util.error('Failed to execute command "%s"' % cmd)
            else:
                Util.warning('Failed to execute command "%s"' % cmd)

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
    def print_cwd():
        Util.info(os.getcwd())

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
        result = Util.execute(cmd, return_out=True, show_cmd=False, exit_on_error=False)
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
    def append_file(file_path, content):
        Util.ensure_file(file_path)

        python_ver = Util.get_python_ver()
        if python_ver[0] == 3:
            types = [str]
        else:
            types = [str, unicode]

        if type(content) in types:
            content = [content]

        f = open(file_path, 'a+')
        for line in content:
            f.write(line + '\n')
        f.close()

    @staticmethod
    def load_json(file_path):
        f = open(file_path)
        content = json.load(f)
        f.close()
        return content

    @staticmethod
    def dump_json(file_path, content, indent=2, sort_keys=False):
        Util.ensure_file(file_path)
        f = open(file_path, 'r+')
        f.seek(0)
        f.truncate()
        json.dump(content, f, indent=indent, sort_keys=sort_keys)
        f.close()

    @staticmethod
    def get_datetime(format='%Y%m%d%H%M%S'):
        return time.strftime(format, time.localtime())

    @staticmethod
    def get_env(env):
        return os.getenv(env)

    @staticmethod
    def set_env(env, value, verbose=False):
        if value:
            os.environ[env] = value
        elif env in os.environ:
            del os.environ[env]

        if verbose:
            Util.info('%s=%s' % (env, value))

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
    # ver is in format a.b.c.d
    # return 1 if ver_a > ver_b
    # return 0 if ver_a == ver_b
    # return -1 if ver_a < ver_b
    def cmp_ver(ver_a, ver_b):
        vers_a = [int(x) for x in ver_a.split('.')]
        vers_b = [int(x) for x in ver_b.split('.')]

        # make sure two lists have same length and add 0s for short one.
        len_a = len(vers_a)
        len_b = len(vers_b)
        len_max = max(len_a, len_b)
        len_diff = abs(len_a - len_b)
        vers_diff = []
        for _ in range(len_diff):
            vers_diff.append(0)
        if len_a < len_b:
            vers_a.extend(vers_diff)
        elif len_b < len_a:
            vers_b.extend(vers_diff)

        index = 0
        while index < len_max:
            if vers_a[index] > vers_b[index]:
                return 1
            elif vers_a[index] < vers_b[index]:
                return -1
            index += 1
        return 0

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

        if isinstance(content, list):
            content = '\n\n'.join(content)

        to_list = to.split(',')
        msg = MIMEMultipart('alternative')
        msg['From'] = sender
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(content, type))

        try:
            smtp = smtplib.SMTP(Util.SMTP_SERVER)
            smtp.sendmail(sender, to_list, msg.as_string())
            Util.info('Email was sent successfully')
        except Exception as e:
            Util.error('Failed to send mail: %s' % e)
        finally:
            smtp.quit()

    @staticmethod
    def get_quotation():
        if Util.HOST_OS == Util.WINDOWS:
            quotation = '\"'
        else:
            quotation = '\''

        return quotation

    @staticmethod
    def format_slash(s):
        if platform.system().lower() == 'windows':
            return s.replace('/', '\\')
        else:
            return s.replace('\\', '/')

    @staticmethod
    @retry(Exception, tries=5, delay=3, backoff=2)
    def urlopen_with_retry(url):
        return urllib2.urlopen(url)

    @staticmethod
    def cal_relative_out_dir(target_arch, target_os, symbol_level=0, no_component_build=False, dcheck=False):
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
    def get_webdriver(browser_name, browser_path='', browser_options='', webdriver_file='', debug=False, target_os=''):
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
            out_dir = Util.cal_relative_out_dir('x86_64', Util.HOST_OS)
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
        # webdriver_file
        if not webdriver_file:
            if target_os == Util.CHROMEOS:
                webdriver_file = '/user/local/chromedriver/chromedriver'
            elif browser_name == 'chrome':
                if Util.HOST_OS == Util.DARWIN:
                    chrome_dir = browser_path.replace('/Chromium.app/Contents/MacOS/Chromium', '')
                else:
                    chrome_dir = os.path.dirname(os.path.realpath(browser_path))
                webdriver_file = '%s%s' % (Util.format_slash(chrome_dir + '/chromedriver'), Util.EXEC_SUFFIX)
            elif target_os in [Util.DARWIN, Util.LINUX, Util.WINDOWS]:
                if 'chrome' in browser_name:
                    webdriver_file = ScriptRepo.CHROMEDRIVER_FILE
                elif 'firefox' in browser_name:
                    webdriver_file = Util.FIREFOXDRIVER_PATH
                elif 'edge' in browser_name:
                    webdriver_file = Util.EDGEDRIVER_PATH
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
                driver = webdriver.Chrome(executable_path=webdriver_file, chrome_options=chrome_options, service_args=service_args)
            elif 'firefox' in browser_name:
                from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
                capabilities = DesiredCapabilities.FIREFOX
                capabilities['marionette'] = True
                # capabilities['binary'] = browser_path
                driver = webdriver.Firefox(capabilities=capabilities, executable_path=webdriver_file)
            elif 'edge' in browser_name:
                driver = webdriver.Edge(webdriver_file)

        if not browser_path:
            Util.error('Could not find module at %s' % browser_path)
        else:
            Util.info('Use module at %s' % browser_path)
        if not webdriver_file:
            Util.error('Could not find webdriver at %s' % webdriver_file)
        else:
            Util.info('Use webdriver at %s' % webdriver_file)
        if not driver:
            Util.error('Could not get webdriver')

        return driver

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

    @staticmethod
    # committer date, instead of author date
    def get_repo_head_date():
        return Util.execute('git log -1 --date=format:"%Y%m%d" --format="%cd"', return_out=True, show_cmd=False)[1].rstrip('\n').rstrip('\r')

    @staticmethod
    def get_repo_head_hash():
        cmd = 'git log --pretty=format:"%H" -1'
        result = Util.execute(cmd, return_out=True, show_cmd=False)
        return result[1].rstrip('\n').rstrip('\r')

    @staticmethod
    def get_repo_rev():
        cmd = 'git rev-list --count HEAD'
        result = Util.execute(cmd, return_out=True, show_cmd=False)
        return result[1].rstrip('\n').rstrip('\r')

    @staticmethod
    def get_repo_hashes():
        cmd = 'git log --pretty=format:"%H" --reverse'
        result = Util.execute(cmd, return_out=True, show_cmd=False)
        return result[1].split('\n')

    @staticmethod
    def get_backup_dir(backup_dir, rev):
        if rev == 'latest':
            rev = -1
            rev_dir = ''
            files = os.listdir(backup_dir)
            for file in files:
                match = re.match(Util.BACKUP_PATTERN, file)
                if match:
                    tmp_rev = int(match.group(1))
                    if tmp_rev > rev:
                        rev_dir = file
                        rev = tmp_rev

            return (rev_dir, rev)
        else:
            files = os.listdir(backup_dir)
            for file in files:
                match = re.search(Util.BACKUP_PATTERN, file)
                if match:
                    rev_dir = file
                    return (rev_dir, rev)
            else:
                Util.error('Could not find mesa build %s' % rev)

    @staticmethod
    def set_mesa(dir, rev=0, type='iris'):
        if rev == 'system':
            Util.ensure_pkg('mesa-vulkan-drivers')
            Util.info('Use system Mesa')
        else:
            (rev_dir, rev) = Util.get_backup_dir(dir, rev)
            mesa_dir = '%s/%s' % (dir, rev_dir)
            Util.set_env('LD_LIBRARY_PATH', '%s/lib:%s/lib/x86_64-linux-gnu' % (mesa_dir, mesa_dir), verbose=True)
            Util.set_env('LIBGL_DRIVERS_PATH', '%s/lib/dri' % mesa_dir, verbose=True)
            Util.set_env('VK_ICD_FILENAMES', '%s/share/vulkan/icd.d/intel_icd.x86_64.json' % mesa_dir, verbose=True)

            if type == 'iris':
                Util.set_env('MESA_LOADER_DRIVER_OVERRIDE', 'iris')
            else:
                Util.set_env('MESA_LOADER_DRIVER_OVERRIDE', 'i965')

            Util.info('Use mesa at %s' % mesa_dir)
        return rev

    @staticmethod
    def cal_backup_dir(rev=0):
        if not rev:
            rev = Util.get_repo_rev()
        return '%s-%s-%s' % (Util.get_repo_head_date(), rev, Util.get_repo_head_hash())

    @staticmethod
    def get_python_ver():
        return [sys.version_info.major, sys.version_info.minor, sys.version_info.micro]

    @staticmethod
    def get_test_result(result_file):
        def _parse_result(key, val, path, fail_fail, fail_pass, pass_fail, pass_pass):
            if 'expected' in val:
                if val['expected'] == 'FAIL' and val['actual'].startswith('FAIL'):
                    fail_fail.append(path)
                elif val['expected'] == 'FAIL' and val['actual'] == 'PASS':
                    fail_pass.append(path)
                elif val['expected'] == 'PASS' and val['actual'].startswith('FAIL'):
                    pass_fail.append(path)
                elif val['expected'] == 'PASS' and val['actual'] == 'PASS':
                    pass_pass.append(path)
            else:
                for new_key, new_val in val.items():
                    _parse_result(new_key, new_val, '%s/%s' % (path, new_key), fail_fail, fail_pass, pass_fail, pass_pass)

        fail_fail = []
        fail_pass = []
        pass_fail = []
        pass_pass = []
        results = []

        try:
            json_result = json.load(open(result_file))
            for key, val in json_result['tests'].items():
                _parse_result(key, val, key, fail_fail, fail_pass, pass_fail, pass_pass)
        except Exception:
            pass_fail.append('All in %s' % result_file)

        return pass_fail, fail_pass, fail_fail, len(pass_pass)

    @staticmethod
    def get_gpu_info():
        name = ''
        driver = ''
        if Util.HOST_OS == Util.LINUX:
            _, name = Util.execute('glxinfo | grep Device', return_out=True)
            name = name.split(':')[1].strip()
            _, driver = Util.execute('glxinfo | grep \'OpenGL version\'', return_out=True)
            match = re.search('(Mesa.*)', driver)
            if match:
                driver = match.group(1)
        elif Util.HOST_OS == Util.WINDOWS:
            name = ''
        return name, driver

    # constants
    MYSQL_SERVER = 'wp-27'
    SMTP_SERVER = 'wp-27.sh.intel.com'
    WINDOWS = 'windows'
    LINUX = 'linux'
    DARWIN = 'darwin'
    CHROMEOS = 'chromeos'
    ANDROID = 'android'
    MAX_REV = 9999999
    BACKUP_PATTERN = r'\d{8}-(\d*)-[a-z0-9]{40}$' # <date>-<rev>-<hash>
    COMMIT_STR = 'commit (.*)'
    HOST_OS = platform.system().lower()
    HOST_OS_RELEASE = '0.0'
    if HOST_OS == LINUX:
        result = subprocess.check_output(['cat', '/etc/lsb-release']).decode('utf-8')
        if re.search(CHROMEOS, result[1]):
            HOST_OS = CHROMEOS

    if HOST_OS == CHROMEOS:
        HOST_OS_RELEASE = platform.platform()
    elif HOST_OS == DARWIN:
        HOST_OS_RELEASE = platform.mac_ver()[0]
    elif HOST_OS == LINUX:
        dist = platform.linux_distribution()
        HOST_OS_RELEASE = '%s %s' % (dist[0], dist[1])
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
    WORKSPACE_DIR = format_slash.__func__(WORKSPACE_DIR)
    BACKUP_DIR =  format_slash.__func__('%s/backup' % WORKSPACE_DIR)
    PROJECT_DIR =  format_slash.__func__('%s/project' % WORKSPACE_DIR)
    PROJECT_ANGLE_DIR =  format_slash.__func__('%s/angle' % PROJECT_DIR)
    PROJECT_AQUARIUM_DIR =  format_slash.__func__('%s/aquarium' % PROJECT_DIR)
    PROJECT_CHROME_DIR =  format_slash.__func__('%s/chromium' % PROJECT_DIR)
    PROJECT_CHROME_SRC_DIR =  format_slash.__func__('%s/src' % PROJECT_CHROME_DIR)
    PROJECT_DAWN_DIR =  format_slash.__func__('%s/dawn' % PROJECT_DIR)
    PROJECT_DEPOT_TOOLS =  format_slash.__func__('%s/depot_tools' % PROJECT_DIR)
    PROJECT_MESA_DIR =  format_slash.__func__('%s/mesa' % PROJECT_DIR)
    PROJECT_MESA_BACKUP_DIR =  format_slash.__func__('%s/backup' % PROJECT_MESA_DIR)
    PROJECT_SKIA_DIR =  format_slash.__func__('%s/skia' % PROJECT_DIR)
    PROJECT_TFJS_DIR =  format_slash.__func__('%s/tfjs' % PROJECT_DIR)
    PROJECT_TOOLKIT_DIR =  format_slash.__func__('%s/toolkit' % PROJECT_DIR)
    PROJECT_V8_DIR =  format_slash.__func__('%s/v8' % PROJECT_DIR)
    PROJECT_WASM_DIR =  format_slash.__func__('%s/wasm' % PROJECT_DIR)
    PROJECT_WEBGL_DIR =  format_slash.__func__('%s/WebGL' % PROJECT_DIR)
    PROJECT_WEBGPUCTS_DIR =  format_slash.__func__('%s/webgpucts' % PROJECT_DIR)
    PROJECT_WEBGPUSPEC_DIR =  format_slash.__func__('%s/webgpuspec' % PROJECT_DIR)
    PROJECT_WEBBENCH_DIR =  format_slash.__func__('%s/webbench' % PROJECT_DIR)
    PROJECT_WORK_DIR =  format_slash.__func__('%s/work' % PROJECT_DIR)
    PROJECT_WPT_DIR =  format_slash.__func__('%s/web-platform-tests' % PROJECT_DIR)
    HOME_DIR = format_slash.__func__(expanduser("~"))

    GNP_SCRIPT =  format_slash.__func__('%s/misc/gnp.py' % PROJECT_TOOLKIT_DIR)
    MESA_SCRIPT = format_slash.__func__('%s/misc/mesa.py' % PROJECT_TOOLKIT_DIR)

    if HOST_OS == WINDOWS:
        APPDATA_DIR = format_slash.__func__(os.getenv('APPDATA'))
        PROGRAMFILES_DIR = format_slash.__func__(os.getenv('PROGRAMFILES'))
        PROGRAMFILESX86_DIR = format_slash.__func__(os.getenv('PROGRAMFILES(X86)'))

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
    ROOT_DIR = Util.format_slash(tmp_dir)
    UTIL_DIR = Util.format_slash('%s/util' % ROOT_DIR)
    TOOL_DIR = Util.format_slash('%s/tool' % UTIL_DIR)
    if Util.HOST_OS == Util.WINDOWS:
        Util.prepend_path(TOOL_DIR)

    IGNORE_DIR = Util.format_slash('%s/ignore' % ROOT_DIR)
    IGNORE_CHROMIUM_DIR = Util.format_slash('%s/chromium' % IGNORE_DIR)
    IGNORE_CHROMIUM_DOWNLOAD_DIR = Util.format_slash('%s/download' % IGNORE_CHROMIUM_DIR)
    IGNORE_LOG_DIR = Util.format_slash('%s/log' % IGNORE_DIR)
    IGNORE_TIMESTAMP_DIR = Util.format_slash('%s/timestamp' % IGNORE_DIR)
    IGNORE_WEBMARK_DIR = Util.format_slash('%s/webmark' % IGNORE_DIR)
    IGNORE_WEBMARK_RESULT_DIR = Util.format_slash('%s/result' % IGNORE_WEBMARK_DIR)

    CONTRIB_DIR = Util.format_slash('%s/contrib' % ROOT_DIR)
    USER_DATA_DIR = Util.format_slash('%s/user-data-dir-%s' % (IGNORE_CHROMIUM_DIR, Util.USER_NAME))
    W3C_DIR = Util.format_slash('%s/w3c' % ROOT_DIR)

    CHROMEDRIVER_FILE = Util.format_slash('%s/webdriver/%s/chromedriver%s' % (TOOL_DIR, Util.HOST_OS, Util.EXEC_SUFFIX))
    IGNORE_BOTO_FILE = Util.format_slash('%s/boto.conf' % IGNORE_DIR)
    IGNORE_FAIL_FILE = Util.format_slash('%s/FAIL' % IGNORE_DIR)

class ChromiumRepo():
    FAKE_REV = 0

    COMMIT_STR = 'commit (.*)'

    INFO_INDEX_MIN_REV = 0
    INFO_INDEX_MAX_REV = 1
    INFO_INDEX_REV_INFO = 2

    # rev_info = {rev: info}
    REV_INFO_INDEX_HASH = 0
    REV_INFO_INDEX_ROLL_REPO = 1
    REV_INFO_INDEX_ROLL_HASH = 2
    REV_INFO_INDEX_ROLL_COUNT = 3

    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.info = [self.FAKE_REV, self.FAKE_REV, {}]

    def get_working_dir_rev(self):
        Util.chdir(self.root_dir)
        cmd = 'git log --shortstat -1'
        return self._get_head_rev(cmd)

    def get_local_repo_rev(self):
        cmd = 'git log --shortstat -1 origin/master'
        return self._get_head_rev(cmd)

    def get_hash_from_rev(self, rev):
        if rev not in self.info[self.INFO_INDEX_REV_INFO]:
            self.get_info(rev)
        return self.info[self.INFO_INDEX_REV_INFO][rev][self.REV_INFO_INDEX_HASH]

    # get info of [min_rev, max_rev]
    def get_info(self, min_rev, max_rev=FAKE_REV):
        if max_rev == self.FAKE_REV:
            max_rev = min_rev

        if min_rev > max_rev:
            return

        info = self.info
        info_min_rev = info[self.INFO_INDEX_MIN_REV]
        info_max_rev = info[self.INFO_INDEX_MAX_REV]
        if info_min_rev <= min_rev and info_max_rev >= max_rev:
            return

        if info[self.INFO_INDEX_MIN_REV] == self.FAKE_REV:
            self._get_info(min_rev, max_rev)
            info[self.INFO_INDEX_MIN_REV] = min_rev
            info[self.INFO_INDEX_MAX_REV] = max_rev
        else:
            if min_rev < info_min_rev:
                self._get_info(min_rev, info_min_rev - 1)
                info[self.INFO_INDEX_MIN_REV] = min_rev
            if max_rev > info_max_rev:
                self._get_info(info_max_rev + 1, max_rev)
                info[self.INFO_INDEX_MAX_REV] = max_rev

    def _get_info(self, min_rev, max_rev):
        info = self.info
        head_rev = self.get_local_repo_rev()
        if max_rev > head_rev:
            Util.error('Revision %s is not ready' % max_rev)
        cmd = 'git log --shortstat origin/master~%s..origin/master~%s ' % (head_rev - min_rev + 1, head_rev - max_rev)
        result = Util.execute(cmd, show_cmd=False, return_out=True)
        lines = result[1].split('\n')

        rev_info = info[self.INFO_INDEX_REV_INFO]
        self._parse_lines(lines, rev_info)

    def _parse_lines(self, lines, rev_info):
        tmp_hash = ''
        tmp_author = ''
        tmp_date = ''
        tmp_subject = ''
        tmp_rev = 0
        tmp_insertion = -1
        tmp_deletion = -1
        tmp_is_roll = False
        for index in range(0, len(lines)):
            line = lines[index]
            if re.match(self.COMMIT_STR, line):
                tmp_hash = ''
                tmp_author = ''
                tmp_date = ''
                tmp_subject = ''
                tmp_rev = 0
                tmp_insertion = -1
                tmp_deletion = -1
                tmp_is_roll = False
            (tmp_rev, tmp_hash, tmp_author, tmp_date, tmp_subject, tmp_insertion, tmp_deletion, tmp_is_roll) = self._parse_line(lines, index, tmp_rev, tmp_hash, tmp_author, tmp_date, tmp_subject, tmp_insertion, tmp_deletion, tmp_is_roll)
            if tmp_deletion >= 0:
                rev_info[tmp_rev] = [tmp_hash, '', '', 0]
                if tmp_is_roll:
                    match = re.match(r'Roll (.*) ([a-zA-Z0-9]+)..([a-zA-Z0-9]+) \((\d+) commits\)', tmp_subject)
                    rev_info[tmp_rev][self.REV_INFO_INDEX_ROLL_REPO] = match.group(1)
                    rev_info[tmp_rev][self.REV_INFO_INDEX_ROLL_HASH] = match.group(3)
                    rev_info[tmp_rev][self.REV_INFO_INDEX_ROLL_COUNT] = int(match.group(4))

    def _parse_line(self, lines, index, tmp_rev, tmp_hash, tmp_author, tmp_date, tmp_subject, tmp_insertion, tmp_deletion, tmp_is_roll):
        line = lines[index]
        strip_line = line.strip()
        # hash
        match = re.match(self.COMMIT_STR, line)
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

    def _get_head_rev(self, cmd):
        result = Util.execute(cmd, show_cmd=False, return_out=True)
        lines = result[1].split('\n')
        rev_info = {}
        self._parse_lines(lines, rev_info=rev_info)
        for key in rev_info:
            return key

class Program(object):
    def __init__(self, parser):
        parser.add_argument('--timestamp', dest='timestamp', help='timestamp', choices=['day', 'second'], default='second')
        parser.add_argument('--log-file', dest='log_file', help='log file')
        parser.add_argument('--proxy', dest='proxy', help='proxy')
        parser.add_argument('--root-dir', dest='root_dir', help='set root directory')
        parser.add_argument('--target-arch', dest='target_arch', help='target arch', choices=['x86', 'arm', 'x86_64', 'arm64'], default='default')
        parser.add_argument('--target-os', dest='target_os', help='target os, choices can be android, linux, chromeos, windows, darwin', default='default')

        parser.epilog = '''
examples:
python %(prog)s --root-dir --target-arch''' + parser.epilog
        parser.formatter_class = argparse.RawTextHelpFormatter
        args = parser.parse_args()
        self.args = args

        if args.timestamp == 'second':
            timestamp = Util.get_datetime()
        elif args.timestamp == 'day':
            timestamp = Util.get_datetime(format='%Y%m%d')
        self.timestamp = timestamp

        if args.log_file:
            log_file = args.log_file
        else:
            script_name = os.path.basename(sys.argv[0]).replace('.py', '')
            log_file = ScriptRepo.IGNORE_LOG_DIR + '/' + script_name + '-' + timestamp + '.log'
        Util.info('Log file: %s' % log_file)
        self.log_file = Util.format_slash(log_file)

        if args.proxy:
            proxy_parts = args.proxy.split(':')
            proxy_address = proxy_parts[0]
            proxy_port = proxy_parts[1]
        else:
            proxy_address = ''
            proxy_port = ''
        self.proxy_address = proxy_address
        self.proxy_port = proxy_port

        if args.root_dir:
            if not os.path.exists(args.root_dir):
                Util.error('root_dir %s does not exist' % args.root_dir)
            root_dir = args.root_dir
        elif os.path.islink(sys.argv[0]):
            root_dir = Util.get_symbolic_link_dir()
        else:
            root_dir = os.path.abspath(os.getcwd())
        Util.chdir(root_dir)
        self.root_dir = Util.format_slash(root_dir)

        target_arch = args.target_arch
        if target_arch == 'default':
            target_arch = 'x86_64'
        self.target_arch = target_arch

        target_os = args.target_os
        if target_os == 'default':
            target_os = Util.HOST_OS
        self.target_os = target_os

        Util.ensure_dir(ScriptRepo.IGNORE_TIMESTAMP_DIR)
        Util.ensure_dir(ScriptRepo.IGNORE_LOG_DIR)

    def _execute(self, cmd, show_cmd=True, exit_on_error=True, return_out=False, show_duration=False, dryrun=False):
        return Util.execute(cmd=cmd, show_cmd=show_cmd, exit_on_error=exit_on_error, return_out=return_out, show_duration=show_duration, dryrun=dryrun, log_file=self.log_file)

    def _set_boto(self):
        if not self.args.proxy:
            return

        boto_file = ScriptRepo.IGNORE_BOTO_FILE
        if not os.path.exists(boto_file):
            lines = [
                '[Boto]',
                'proxy = %s' % self.proxy_address,
                'proxy_port = %s' % self.proxy_port,
                'proxy_rdns = True',
            ]
            Util.append_file(boto_file, lines)

        Util.set_env('NO_AUTH_BOTO_CONFIG', boto_file)

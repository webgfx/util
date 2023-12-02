import atexit
import urllib2
import re
import socket
import subprocess
from telemetry.internal.browser import browser_finder, browser_options
from selenium import webdriver

CHROMEDRIVER_EXE_PATH = '/usr/local/chromedriver/chromedriver'


class chromedriver(object):
    def __init__(self, extra_chrome_flags=[], username=None, password=None):
        self._chrome = Chrome(username=username, password=password, extra_browser_args=extra_chrome_flags)
        self._browser = self._chrome._browser
        self._browser.tabs[0].Close()
        self._server = chromedriver_server(CHROMEDRIVER_EXE_PATH)
        urllib2.urlopen('http://localhost:%i/json/new' % get_chrome_remote_debugging_port())
        chromeOptions = {'debuggerAddress': ('localhost:%d' % get_chrome_remote_debugging_port())}
        capabilities = {'chromeOptions': chromeOptions}
        self.driver = webdriver.Remote(command_executor=self._server.url, desired_capabilities=capabilities)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.driver.close()
        del self.driver
        self._server.close()
        del self._server
        self._browser.Close()
        del self._browser


class chromedriver_server(object):
    def __init__(self, exe_path):
        chromedriver_args = [exe_path]
        port = get_unused_port()
        chromedriver_args.append('--port=%d' % port)
        self.url = 'http://localhost:%d' % port
        self.sp = subprocess.Popen(
            chromedriver_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, env=None
        )
        atexit.register(self.close)

    def close(self):
        try:
            urllib2.urlopen(self.url + '/shutdown', timeout=10).close()
        except:
            pass
        self.sp.stdout.close()
        self.sp.stderr.close()


class Chrome(object):
    def __init__(self, extra_browser_args=None, username=None, password=None):
        finder_options = browser_options.BrowserFinderOptions()
        finder_options.browser_type = 'system'
        if extra_browser_args:
            finder_options.browser_options.AppendExtraBrowserArgs(extra_browser_args)
        finder_options.verbosity = 0
        finder_options.CreateParser().parse_args(args=[])
        b_options = finder_options.browser_options
        b_options.disable_component_extensions_with_background_pages = False
        b_options.create_browser_with_oobe = True
        b_options.clear_enterprise_policy = True
        b_options.dont_override_profile = False
        b_options.disable_gaia_services = True
        b_options.disable_default_apps = True
        b_options.disable_component_extensions_with_background_pages = True
        b_options.auto_login = True
        b_options.gaia_login = False
        b_options.gaia_id = b_options.gaia_id
        open('/mnt/stateful_partition/etc/collect_chrome_crashes', 'w').close()
        browser_to_create = browser_finder.FindBrowser(finder_options)
        self._browser = browser_to_create.Create(finder_options)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_chrome_remote_debugging_port():
    chromepid = int(subprocess.check_output(['pgrep', '-o', '^chrome$']))
    command = subprocess.check_output(['ps', '-p', str(chromepid), '-o', 'command='])
    matches = re.search('--remote-debugging-port=([0-9]+)', command)
    if matches:
        return int(matches.group(1))


def get_unused_port():
    def try_bind(port, socket_type, socket_proto):
        s = socket.socket(socket.AF_INET, socket_type, socket_proto)
        try:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('', port))
                return s.getsockname()[1]
            except socket.error:
                return None
        finally:
            s.close()

    while True:
        port = try_bind(0, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        if port and try_bind(port, socket.SOCK_DGRAM, socket.IPPROTO_UDP):
            return port

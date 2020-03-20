# Copyright (C) 2020 OpenMotics BV
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import logging
import socket
import ssl
import time

import psutil
import pytest

logger = logging.getLogger('openmotics')


def check_ip_range():
    # type: () -> bool
    addresses = ([x.address for x in xs if x.broadcast == '10.91.115.255'] for xs in psutil.net_if_addrs().values())
    return not sum(addresses, [])


@pytest.fixture
def power_on(request, toolbox):
    yield
    toolbox.ensure_power_on()
    toolbox.dut.login()


@pytest.fixture
def discover_mode(request, toolbox):
    yield
    toolbox.dut.get('/module_discover_stop')


@pytest.fixture
def authorized_mode(request, toolbox):
    yield
    toolbox.wait_authorized_mode()


@pytest.fixture
def maintenance_mode(request, toolbox):
    yield
    for _ in xrange(10):
        data = toolbox.dut.get('/get_status', success=False)
        if data['success']:
            break
        time.sleep(0.2)
    assert data['success']


@pytest.mark.slow
def test_power_cycle(toolbox, power_on):
    toolbox.power_off()
    toolbox.ensure_power_on()
    pending = toolbox.health_check()
    assert pending == []


@pytest.mark.smoke
def test_module_discover_noop(toolbox, discover_mode):
    logger.info('start module discovery')
    toolbox.start_module_discovery()

    data = toolbox.dut.get('/module_discover_status')
    assert data['running']
    toolbox.discover_input_module()
    toolbox.discover_output_module()

    for _ in xrange(10):
        data = toolbox.dut.get('/get_modules')
        if data.get('inputs') and data.get('outputs'):
            break
        time.sleep(0.2)

    assert 'inputs' in data
    assert 'I' in data['inputs']
    assert 'outputs' in data
    assert 'O' in data['outputs']


@pytest.mark.slow
@pytest.mark.skipif(check_ip_range(), reason='the maintenance ports are not accessible on jenkins')
def test_maintenance(toolbox, maintenance_mode):
    data = toolbox.dut.get('/get_status')
    expected_version = 'F{} H{}'.format(data['version'], data['hw_version'])

    logger.info('start maintenance')
    data = toolbox.dut.get('/open_maintenance')
    assert 'port' in data

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)

    time.sleep(2)
    ssl_sock = ssl.wrap_socket(
        sock,
        ssl_version=ssl.PROTOCOL_SSLv23,
        do_handshake_on_connect=False,
        suppress_ragged_eofs=False
    )
    ssl_sock.connect((toolbox.dut._host, data['port']))

    def readline():
        c, buf = ('', '')
        while c != '\n':
            c = ssl_sock.recv(1)
            buf += c
        return buf.strip()

    data = ''
    while data != 'OK':
        data = readline()
        logger.debug('received data "{}"'.format(data))

    ssl_sock.send('firmware version\r\n')
    assert readline() == 'firmware version'
    assert readline() == expected_version

    # not allowed during maintenance
    data = toolbox.dut.get('/get_status', success=False)
    assert data['msg'] == 'maintenance_mode'

    ssl_sock.send('exit\r\n')
    ssl_sock.close()


@pytest.mark.slow
def test_authorized_mode(toolbox, authorized_mode):
    data = toolbox.dut.get('/get_usernames', success=False)
    assert not data['success'] and data['msg'] == 'unauthorized'

    toolbox.start_authorized_mode()
    data = toolbox.dut.get('/get_usernames')
    assert 'openmotics' in data['usernames']


@pytest.fixture
def create_user(request, toolbox):
    try:
        toolbox.dut.login(success=False)
    except Exception:
        toolbox.start_authorized_mode()
        toolbox.create_or_update_user()
        toolbox.dut.login()
    yield


@pytest.mark.slow
def test_factory_reset(toolbox, create_user):
    logger.info('factory reset')
    data = toolbox.factory_reset()
    assert data['factory_reset'] == 'pending'
    time.sleep(60)
    toolbox.health_check(timeout=300)

    toolbox.start_authorized_mode()
    data = toolbox.dut.get('/get_usernames', use_token=False)
    logger.info('users after reset {}'.format(data['usernames']))
    toolbox.create_or_update_user()
    toolbox.dut.login()

    data = toolbox.dut.get('/get_modules')
    assert 'inputs' in data
    assert data['inputs'] == []
    assert 'outputs' in data
    assert data['outputs'] == []

    logger.info('start module discover')
    toolbox.dut.get('/module_discover_start')
    time.sleep(2)
    toolbox.discover_input_module()
    time.sleep(0.2)
    toolbox.discover_output_module()
    time.sleep(2)
    data = toolbox.dut.get('/get_modules')
    assert 'inputs' in data
    assert 'I' in data['inputs']
    assert 'outputs' in data
    assert 'O' in data['outputs']

    toolbox.dut.get('/module_discover_stop')
    time.sleep(2)
    data = toolbox.dut.get('/get_modules_information')
    modules = data['modules']['master'].values()
    assert set(['I', 'O']) == set(x['type'] for x in modules)
    assert None not in [x['firmware'] for x in modules]

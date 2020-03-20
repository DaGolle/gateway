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
import os
import time
from datetime import datetime

import requests
import ujson as json
from requests.exceptions import ConnectionError, RequestException

logger = logging.getLogger('openmotics')

if False:  # MYPY
    from typing import Any, Dict, List, Optional, Tuple


class Client(object):
    def __init__(self, host, auth=None):
        # type: (str, List[str]) -> None
        self._host = host
        self._auth = auth
        self._default_kwargs = {'verify': False}
        self._token = None  # type: Optional[str]

    @property
    def token(self):
        # type: () -> Optional[str]
        if self._token is None:
            self._token = self.login()
        return self._token

    def login(self, success=True, timeout=30):
        # type: (bool, float) -> Optional[str]
        if self._auth:
            self._token = None
            params = {'username': self._auth[0], 'password': self._auth[1], 'accept_terms': True}
            data = self.get('/login', params=params, use_token=False, success=success, timeout=timeout)
            if 'token' in data:
                return data['token']
            else:
                raise Exception('unexpected response {}'.format(data))
        else:
            return None

    def get(self, path, params=None, headers=None, success=True, use_token=True, timeout=30):
        # type: (str, Dict[str,Any], Dict[str,Any], bool, bool, float) -> Any
        params = params or {}
        headers = headers or {}
        uri = 'https://{}{}'.format(self._host, path)
        if use_token:
            headers['Authorization'] = 'Bearer {}'.format(self.token)
            logger.debug('GET {} {}'.format(path, params))

        since = time.time()
        while since > time.time() - timeout:
            try:
                response = requests.get(uri, params=params, headers=headers, **self._default_kwargs)
                data = response.json()
                if success and 'success' in data:
                    assert data['success'], 'content={}'.format(response.content)
                return data
            except (AssertionError, ConnectionError, RequestException) as exc:
                logger.debug('request {} failed {}, retrying...'.format(path, exc))
                time.sleep(16)
                pass
        raise AssertionError('request {} failed after {:.2f}s'.format(path, time.time() - since))


class TesterGateway(object):
    def __init__(self, client):
        # type: (Client) -> None
        self._client = client
        self._last_received_at = 0.0
        self._last_data = {}  # type: Dict[str,Any]
        self._outputs = {}  # type: Dict[int,bool]
        self.update_events()

    def get_last_outputs(self):
        # type: () -> List[str]
        if self._last_data:
            outputs = self._last_data['events'][-1]['outputs']
            return ['?' if x is None else str(x) for x in outputs]
        else:
            return []

    def get(self, path, params=None, headers=None, success=True, use_token=True):
        # type: (str, Dict[str,Any], Dict[str,Any], bool, bool) -> Any
        return self._client.get(path, params=params, headers=headers, success=True, use_token=use_token)

    def log_events(self):
        # type: () -> None
        for event in (x for x in self._last_data['events'] if 'output_id' in x):
            received_at, output_id, output_status, outputs = (event['received_at'], event['output_id'], event['output_status'], event['outputs'])
            timestamp = datetime.fromtimestamp(received_at).strftime('%y-%m-%d %H:%M:%S,%f')
            state = ' '.join('?' if x is None else str(x) for x in outputs)
            logger.error('{} received event o#{} -> {}    outputs={}'.format(timestamp, output_id, output_status, state))

    def update_events(self):
        # type: () -> bool
        data = self.get('/plugins/event_observer/events')
        self._last_data = data
        changed = False
        for event in (x for x in self._last_data['events'] if 'output_id' in x):
            received_at, output_id, output_status = (event['received_at'], event['output_id'], event['output_status'])
            if received_at >= self._last_received_at:
                changed = True
                self._last_received_at = received_at
                self._outputs[output_id] = bool(output_status)
        return changed

    def reset(self):
        # type: () -> None
        self._outputs = {}

    def receive_output_event(self, output_id, output_status, between):
        # type: (int, bool, Tuple[float, float]) -> bool
        cooldown, deadline = between
        timeout = deadline - cooldown
        if cooldown > 0:
            logger.info('waiting {:.2f}s before event'.format(cooldown))
            self.reset()
            time.sleep(cooldown)
        since = time.time()
        while since > time.time() - timeout:
            if output_id in self._outputs and output_status == self._outputs[output_id]:
                logger.info('received event o#{} status={} after {:.2f}s'.format(output_id, self._outputs[output_id], time.time() - since))
                return True
            if self.update_events():
                continue
            time.sleep(0.2)
        logger.error('receive event o#{} status={}, timeout after {:.2f}s'.format(output_id, output_status, time.time() - since))
        self.log_events()
        return False


class Toolbox(object):
    DEBIAN_AUTHORIZED_MODE = 13
    DEBIAN_DISCOVER_INPUT = 14
    DEBIAN_DISCOVER_OUTPUT = 15
    DEBIAN_POWER_OUTPUT = 8

    def __init__(self):
        # type: () -> None
        self._tester = None  # type: Optional[TesterGateway]
        self._dut = None  # type: Optional[Client]
        self._dut_inputs = None  # type: Optional[List[int]]
        self._dut_outputs = None  # type: Optional[List[int]]

    @property
    def tester(self):
        # type: () -> TesterGateway
        if self._tester is None:
            tester_auth = os.environ['OPENMOTICS_TESTER_AUTH'].split(':')
            tester_host = os.environ['OPENMOTICS_TESTER_HOST']
            self._tester = TesterGateway(Client(tester_host, auth=tester_auth))
        return self._tester

    @property
    def dut(self):
        # type: () -> Client
        if self._dut is None:
            dut_auth = os.environ['OPENMOTICS_DUT_AUTH'].split(':')
            dut_host = os.environ['OPENMOTICS_DUT_HOST']
            self._dut = Client(dut_host, auth=dut_auth)
        return self._dut

    @property
    def dut_inputs(self):
        # type: () -> List[int]
        if self._dut_inputs is None:
            input_modules = self.list_modules('I')
            self._dut_inputs = range(0, len(input_modules) * 8 - 1)
        return self._dut_inputs

    @property
    def dut_outputs(self):
        if self._dut_outputs is None:
            output_modules = self.list_modules('O')
            self._dut_outputs = range(0, len(output_modules) * 8 - 1)
        return self._dut_outputs

    def initialize(self):
        # type: () -> None
        self.ensure_power_on()
        try:
            self.dut.login(success=False)
        except Exception:
            logger.info('initializing gateway...')
            self.start_authorized_mode()
            self.create_or_update_user()
            self.dut.login()
        try:
            data = self.dut.get('/get_modules')
            data['inputs'][0]
            data['outputs'][0]
        except Exception:
            logger.info('initializing modules...')
            self.start_module_discovery()
            self.discover_input_module()
            self.discover_output_module()
            time.sleep(2)
            self.dut.get('/module_discover_stop')

    def factory_reset(self, confirm=True):
        # type: (bool) -> Dict[str,Any]
        assert self.dut._auth
        params = {'username': self.dut._auth[0], 'password': self.dut._auth[1], 'confirm': confirm}
        return self.dut.get('/factory_reset', params=params, success=confirm)

    def list_modules(self, module_type, min_modules=1):
        # type: (str, int) -> List[Dict[str,Any]]
        data = self.dut.get('/get_modules_information')
        modules = [x for x in data['modules']['master'].values() if x['type'] == module_type and x['firmware']]
        assert len(modules) >= min_modules, 'Not enough modules of type {} available'.format(module_type)
        return modules

    def start_authorized_mode(self):
        # type: () -> None
        logger.info('start authorized mode')
        self.tester.get('/set_output', {'id': self.DEBIAN_AUTHORIZED_MODE, 'is_on': True})
        time.sleep(15)
        self.tester.get('/set_output', {'id': self.DEBIAN_AUTHORIZED_MODE, 'is_on': False})

    def wait_authorized_mode(self, timeout=240):
        # type: (float) -> None
        logger.debug('wait for authorized mode timeout')
        since = time.time()
        while since > time.time() - timeout:
            data = self.dut.get('/get_usernames', success=False)
            if not data['success'] and data.get('msg') == 'unauthorized':
                return
            logger.debug('authorized mode still active, waiting {}'.format(data))
            time.sleep(10)
        raise AssertionError('authorized mode still activate after {:.2f}s'.format(time.time() - since))

    def create_or_update_user(self, success=True):
        # type: (bool) -> None
        logger.info('create or update test user')
        assert self.dut._auth
        user_data = {'username': self.dut._auth[0], 'password': self.dut._auth[1]}
        self.dut.get('/create_user', params=user_data, use_token=False, success=success)

    def start_module_discovery(self):
        # type: () -> None
        self.dut.get('/module_discover_start')
        for _ in xrange(10):
            data = self.dut.get('/module_discover_status')
            if data['running']:
                return
            time.sleep(0.2)

    def discover_input_module(self):
        # type: () -> None
        self.press_input(self.DEBIAN_DISCOVER_INPUT)

    def discover_output_module(self):
        # type: () -> None
        self.press_input(self.DEBIAN_DISCOVER_OUTPUT)

    def power_off(self):
        # type: () -> None
        logger.info('power off')
        self.tester.get('/set_output', {'id': self.DEBIAN_POWER_OUTPUT, 'is_on': False})
        time.sleep(2)

    def ensure_power_on(self):
        # type: () -> None
        if self.health_check(timeout=0.2) == []:
            return
        logger.info('power on')
        self.tester.get('/set_output', {'id': self.DEBIAN_POWER_OUTPUT, 'is_on': True})
        logger.info('wait for gateway api to respond')
        self.health_check(timeout=300)
        logger.info('health check done')

    def health_check(self, timeout=30):
        # type: (float) -> List[str]
        since = time.time()
        pending = ['unknown']
        while since > time.time() - timeout:
            try:
                data = self.dut.get('/health_check', use_token=False, timeout=timeout)
                pending = [k for k, v in data['health'].items() if not v['state']]
                if pending == []:
                    return pending
                logger.debug('wait for health check, {}'.format(pending))
            except Exception:
                pass
            time.sleep(10)
        return pending

    def configure_output(self, output_id, config):
        # type: (int, Dict[str,Any]) -> None
        config_data = {'id': output_id}
        config_data.update(**config)
        logger.info('configure output o#{} with {}'.format(output_id, config))
        self.dut.get('/set_output_configuration', {'config': json.dumps(config_data)})

    def ensure_output(self, output_id, status, config=None):
        # type: (int, int, Optional[Dict[str,Any]]) -> None
        if config:
            self.configure_output(output_id, config)
        state = ' '.join(self.tester.get_last_outputs())
        logger.info('ensure output o#{} is {}    outputs={}'.format(output_id, status, state))
        time.sleep(0.2)
        self.set_output(output_id, status)
        self.tester.reset()

    def set_output(self, output_id, status):
        # type: (int, int) -> None
        logger.info('set output o#{} -> {}'.format(output_id, status))
        self.dut.get('/set_output', {'id': output_id, 'is_on': status})

    def press_input(self, input_id):
        # type: (int) -> None
        self.tester.get('/set_output', {'id': input_id, 'is_on': False})  # ensure start status
        self.tester.reset()
        self.tester.get('/set_output', {'id': input_id, 'is_on': True})
        time.sleep(0.2)
        self.tester.get('/set_output', {'id': input_id, 'is_on': False})
        logger.info('toggled i#{} -> True -> False'.format(input_id))

    def assert_output_changed(self, output_id, status, between=(0, 30)):
        # type: (int, bool, Tuple[float,float]) -> None
        if self.tester.receive_output_event(output_id, status, between=between):
            return
        raise AssertionError('expected event o#{} status={}'.format(output_id, status))

    def assert_output_status(self, output_id, status, timeout=30):
        # type: (int, bool, float) -> None
        since = time.time()
        while since > time.time() - timeout:
            data = self.dut.get('/get_output_status')
            current_status = data['status'][output_id]['status']
            if bool(status) == bool(current_status):
                logger.info('get output status o#{} status={}, after {:.2f}s'.format(output_id, status, time.time() - since))
                return
            time.sleep(2)
        state = ' '.join(self.tester.get_last_outputs())
        logger.error('get status o#{} status={} != expected {}, timeout after {:.2f}s    outputs={}'.format(output_id, bool(current_status), status, time.time() - since, state))
        self.tester.log_events()
        raise AssertionError('get status o#{} status={} != expected {}, timeout after {:.2f}s'.format(output_id, bool(current_status), status, time.time() - since))

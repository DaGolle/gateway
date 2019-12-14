import logging
from threading import Lock
from simple_pid import PID
from gateway.thermostat.valve import Valve

logger = logging.getLogger('openmotics')


class ThermostatPid(object):

    DEFAULT_KP = 5.0
    DEFAULT_KI = 0.0
    DEFAULT_KD = 2.0

    def __init__(self, thermostat, gateway_api):
        self._gateway_api = gateway_api
        self._thermostat_change_lock = Lock()
        self._heating_valves = []
        self._cooling_valves = []
        self._pid = None
        self._thermostat = None
        self.update_thermostat(thermostat)

    @property
    def enabled(self):
        # 1. sensor is valid
        # 2. outputs configured (heating or cooling)
        if self._thermostat.sensor == 255:
            return False
        if len(self._heating_valves) == 0 and len(self._cooling_valves):
            return False
        return True

    def update_thermostat(self, thermostat):
        with self._thermostat_change_lock:
            self._heating_valves = [Valve(heating_valve, self._gateway_api) for heating_valve in thermostat.heating_valves]
            self._cooling_valves = [Valve(cooling_valve, self._gateway_api) for cooling_valve in thermostat.cooling_valves]

            pid_p = thermostat.pid_p if thermostat.pid_p else self.DEFAULT_KP
            pid_i = thermostat.pid_i if thermostat.pid_i else self.DEFAULT_KI
            pid_d = thermostat.pid_d if thermostat.pid_d else self.DEFAULT_KD
            if self._pid is None:
                self._pid = PID(pid_p, pid_i, pid_d, setpoint=thermostat.setpoint)
            else:
                self._pid.Kp = pid_p
                self._pid.Ki = pid_i
                self._pid.Kd = pid_d
                self._pid.setpoint = thermostat.setpoint
            self._pid.output_limits = (-100, 100)
            self._thermostat = thermostat

    @property
    def thermostat(self):
        return self._thermostat

    @staticmethod
    def _open_valves_cascade(total_percentage, valves):
        n_valves = len(valves)
        percentage_per_valve = 100.0 / n_valves
        n_valves_fully_open = int(total_percentage / percentage_per_valve)
        last_valve_open_percentage = (total_percentage - n_valves_fully_open * percentage_per_valve) / percentage_per_valve
        for n in xrange(n_valves_fully_open):
            valve = valves[n]
            valve.set(100)
        for n in xrange(n_valves_fully_open, n_valves):
            valve = valves(n)
            percentage = last_valve_open_percentage if n == n_valves_fully_open else 0
            valve.set(percentage)

    def _open_valves_equal(self, percentage, valves):
        for valve in valves:
            logger.info('opening valve {} for {}%'.format(valve, percentage))
            valve.set(percentage)

    def _open_valves(self, percentage, valves):
        self._open_valves_equal(percentage, valves)

    def steer(self, power):
        logger.info('PID steer - power {} '.format(power))
        if power > 0:
            # TODO: check union to avoid opening same valves in heating and cooling
            self._open_valves(0, self._cooling_valves)
            self._open_valves(power, self._heating_valves)
        else:
            self._open_valves(0, self._heating_valves)
            self._open_valves(power, self._cooling_valves)

    def switch_off(self):
        self.steer(0)

    def tick(self):
        logger.info('_tick - thermostat {} is {} enabled'.format(self.thermostat.number, '' if self.enabled else 'not'))
        if self.enabled:
            current_temperature = self._gateway_api.get_sensor_temperature_status(self.thermostat.sensor)
            output_power = self._pid(current_temperature)
            logger.info('_tick - PID output power {} '.format(output_power))

            # heating needed while in cooling mode OR
            # cooling needed while in heating mode
            # -> no active aircon required, rely on losses of system to reach equilibrium
            if (self.thermostat.mode == 'cooling' and output_power > 0) or \
               (self.thermostat.mode == 'heating' and output_power < 0):
                output_power = 0
            self.steer(output_power)
        else:
            self.switch_off()

    @property
    def number(self):
        return self.thermostat.number

    @property
    def setpoint(self):
        return self._pid.setpoint

    @setpoint.setter
    def setpoint(self, setpoint):
        self._pid.setpoint = setpoint
        if self.thermostat.setpoint != setpoint:
            # TODO: do we want to store this on every change?
            self.thermostat.setpoint = setpoint
            self.thermostat.save()

    @property
    def Kp(self):
        return self._pid.Kp

    @Kp.setter
    def Kp(self, Kp):
        self._pid.Kp = Kp

    @property
    def Ki(self):
        return self._pid.Ki

    @Ki.setter
    def Ki(self, Ki):
        self._pid.Ki = Ki

    @property
    def Kd(self):
        return self._pid.Kd

    @Kd.setter
    def Kd(self, Kd):
        self._pid.Kd = Kd

    def update_pid_params(self, Kp, Ki, Kd):
        self._pid.tunings = (Kp, Ki, Kd)

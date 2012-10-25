'''
The physical frontend modules communicates over dbus with the leds service,
the PhysicalFrontend class can be used to set the status of the leds or read
the authorized mode.

Created on Sep 23, 2012

@author: fryckbos
'''
import dbus
import sys

def check_for_errors(default_ret):
    """ Decorator that checks if dbus is active and catches exceptions.
    If an exception is thrown, default_ret is returned.
    """
    def wrapped(func):
        """ Wrapped function. """
        def new_func(self, *args, **kwargs):
            """ New function checks bus and catches exceptions. """
            if self.bus == None:
                self.bus = self.get_bus()
            if self.bus != None:
                try:
                    return func(self, *args, **kwargs)
                except:
                    sys.stderr.write("Failed to communicate with physical_frontend_service\n")
                    self.bus = None
            return default_ret
        return new_func
    return wrapped

class PhysicalFrontend:
    """ Communicates with the leds service using dbus. """
    
    LEDS = [ 'uart4', 'uart5', 'vpn', 'stat1', 'stat2', 'alive', 'cloud' ]

    def __init__(self):
        self.bus = self.get_bus()
    
    def get_bus(self):
        """" Try to get the dbus interface to the led_service. 
        
        :returns: None on Exception
        """
        try:
            system_bus = dbus.SystemBus()
            return system_bus.get_object('com.openmotics.status', '/com/openmotics/status')
        except:
            sys.stderr.write("Could not initialize dbus to physical_frontend_service\n")
            return None
        
    @check_for_errors(None)
    def set_led(self, led_name, enabled):
        """ Set the status of a LED. """
        self.bus.set_led(led_name, enabled, dbus_interface='com.openmotics.status')
            
    @check_for_errors(None)
    def toggle_led(self, led_name):
        """ Toggle the status of a LED. """
        self.bus.toggle_led(led_name, dbus_interface='com.openmotics.status')
    
    @check_for_errors(None)
    def serial_activity(self, uart):
        """ Register serial activity on a given UART. """
        self.bus.serial_activity(uart, dbus_interface='com.openmotics.status')
    
    @check_for_errors(False)
    def in_authorized_mode(self):
        """ Check if the gateway is in authorized mode. """
        return self.bus.in_authorized_mode(dbus_interface='com.openmotics.status')
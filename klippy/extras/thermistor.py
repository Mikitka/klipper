# Temperature measurements with thermistors
#
# Copyright (C) 2016-2018  Kevin O'Connor <kevin@koconnor.net>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import math

KELVIN_TO_CELCIUS = -273.15
SAMPLE_TIME = 0.001
SAMPLE_COUNT = 8
REPORT_TIME = 0.300

# Analog voltage to temperature converter for thermistors
class Thermistor:
    def __init__(self, config, params):
        self.pullup = config.getfloat('pullup_resistor', 4700., above=0.)
        ppins = config.get_printer().lookup_object('pins')
        self.mcu_adc = ppins.setup_pin('adc', config.get('sensor_pin'))
        self.mcu_adc.setup_adc_callback(REPORT_TIME, self.adc_callback)
        self.temperature_callback = None
        self.c1 = self.c2 = self.c3 = 0.
        if 'beta' in params:
            self.calc_coefficients_beta(params)
        else:
            self.calc_coefficients(params)
    def calc_coefficients(self, params):
        # Calculate Steinhart-Hart coefficents from temp measurements.
        # Arrange samples as 3 linear equations and solve for c1, c2, and c3.
        inv_t1 = 1. / (params['t1'] - KELVIN_TO_CELCIUS)
        inv_t2 = 1. / (params['t2'] - KELVIN_TO_CELCIUS)
        inv_t3 = 1. / (params['t3'] - KELVIN_TO_CELCIUS)
        ln_r1 = math.log(params['r1'])
        ln_r2 = math.log(params['r2'])
        ln_r3 = math.log(params['r3'])
        ln3_r1, ln3_r2, ln3_r3 = ln_r1**3, ln_r2**3, ln_r3**3

        inv_t12, inv_t13 = inv_t1 - inv_t2, inv_t1 - inv_t3
        ln_r12, ln_r13 = ln_r1 - ln_r2, ln_r1 - ln_r3
        ln3_r12, ln3_r13 = ln3_r1 - ln3_r2, ln3_r1 - ln3_r3

        self.c3 = ((inv_t12 - inv_t13 * ln_r12 / ln_r13)
                   / (ln3_r12 - ln3_r13 * ln_r12 / ln_r13))
        self.c2 = (inv_t12 - self.c3 * ln3_r12) / ln_r12
        self.c1 = inv_t1 - self.c2 * ln_r1 - self.c3 * ln3_r1
    def calc_coefficients_beta(self, params):
        # Calculate equivalent Steinhart-Hart coefficents from beta
        inv_t1 = 1. / (params['t1'] - KELVIN_TO_CELCIUS)
        ln_r1 = math.log(params['r1'])
        self.c3 = 0.
        self.c2 = 1. / params['beta']
        self.c1 = inv_t1 - self.c2 * ln_r1
    def setup_minmax(self, min_temp, max_temp):
        adc_range = [self.calc_adc(min_temp), self.calc_adc(max_temp)]
        self.mcu_adc.setup_minmax(SAMPLE_TIME, SAMPLE_COUNT,
                                  minval=min(adc_range), maxval=max(adc_range))
    def setup_callback(self, temperature_callback):
        self.temperature_callback = temperature_callback
    def get_report_time_delta(self):
        return REPORT_TIME
    def adc_callback(self, read_time, read_value):
        # Calculate temperature from adc
        adc = max(.00001, min(.99999, read_value))
        r = self.pullup * adc / (1.0 - adc)
        ln_r = math.log(r)
        inv_t = self.c1 + self.c2 * ln_r + self.c3 * ln_r**3
        temp = 1.0/inv_t + KELVIN_TO_CELCIUS
        self.temperature_callback(read_time + SAMPLE_COUNT * SAMPLE_TIME, temp)
    def calc_adc(self, temp):
        inv_t = 1. / (temp - KELVIN_TO_CELCIUS)
        if self.c3:
            # Solve for ln_r using Cardano's formula
            y = (self.c1 - inv_t) / (2. * self.c3)
            x = math.sqrt((self.c2 / (3. * self.c3))**3 + y**2)
            ln_r = math.pow(x - y, 1./3.) - math.pow(x + y, 1./3.)
        else:
            ln_r = (inv_t - self.c1) / self.c2
        r = math.exp(ln_r)
        return r / (self.pullup + r)

Sensors = {
    "EPCOS 100K B57560G104F": {
        't1': 25., 'r1': 100000., 't2': 150., 'r2': 1641.9,
        't3': 250., 'r3': 226.15 },
    "ATC Semitec 104GT-2": {
        't1': 20., 'r1': 126800., 't2': 150., 'r2': 1360.,
        't3': 300., 'r3': 80.65 },
    "NTC 100K beta 3950": { 't1': 25., 'r1': 100000., 'beta': 3950. },
}

def load_config(config):
    # Register default thermistor types
    pheater = config.get_printer().lookup_object("heater")
    for sensor_type, params in Sensors.items():
        func = (lambda config, params=params: Thermistor(config, params))
        pheater.add_sensor(sensor_type, func)

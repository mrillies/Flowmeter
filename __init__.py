# -*- coding: utf-8 -*-
# Flowmeter plugin for Craftbeerpi 
# Version 1.5 made by nanab
# https://github.com/nanab/Flowmeter
# Some code taken from https://github.com/adafruit/Kegomatic


import time
from modules import cbpi
from modules.core.hardware import ActorBase, SensorPassive
from modules.core.step import StepBase
import json
from flask import Blueprint, render_template, jsonify, request
from modules.core.props import Property, StepProperty

blueprint = Blueprint('flowmeter', __name__)
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
except Exception as e:
    print e
    pass


class FlowMeterData():
    SECONDS_IN_A_MINUTE = 60
    MS_IN_A_SECOND = 1000.0
    enabled = True
    clicks = 0
    lastClick = 0
    clickDelta = 0
    hertz = 0.0
    flow = 0  # in Liters per second
    pour = 0.0  # in Liters

    def __init__(self):
        self.clicks = 0
        self.lastClick = int(time.time() * FlowMeterData.MS_IN_A_SECOND)
        self.clickDelta = 0
        self.hertz = 0.0
        self.flow = 0.0
        self.pour = 0.0
        self.enabled = True

    def update(self, currentTime, hertzProp):
        #print hertzProp
        self.clicks += 1
        # get the time delta
        self.clickDelta = max((currentTime - self.lastClick), 1)
        # calculate the instantaneous speed
        if self.enabled is True and self.clickDelta < 1000:
            self.hertz = FlowMeterData.MS_IN_A_SECOND / self.clickDelta
            self.flow = self.hertz / (FlowMeterData.SECONDS_IN_A_MINUTE * hertzProp)  # In Liters per second
            instPour = self.flow * (self.clickDelta / FlowMeterData.MS_IN_A_SECOND)  
            self.pour += instPour
        # Update the last click
        self.lastClick = currentTime

    def clear(self):
        self.pour = 0
        return str(self.pour)


@cbpi.sensor
class Flowmeter(SensorPassive):
    fms = dict()
    gpio = Property.Select("GPIO", options=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27])
    sensorShow = Property.Select("Flowmeter display", options=["Total volume", "Flow, unit/s"])
    hertzProp = Property.Text("Hertz (Default value is 7.5) Requires restart!", configurable=True, default_value="7.5", description="Here you can adjust the hertz for the flowmeter. Whit this value you can calibrate the sensor.")
    def init(self):
        unit = cbpi.get_config_parameter("flowunit", None)
        if unit is None:
            print "INIT FLOW DB"
            try:
                cbpi.add_config_parameter("flowunit", "L", "select", "Flowmeter unit", options=["L", "gal(us)", "gal(uk)", "qt"])
            except:
                cbpi.notify("Flowmeter Error", "Unable to update database.", type="danger", timeout=None)
        try:
            GPIO.setup(int(self.gpio),GPIO.IN, pull_up_down = GPIO.PUD_UP)
            GPIO.add_event_detect(int(self.gpio), GPIO.RISING, callback=self.doAClick, bouncetime=20)
            self.fms[int(self.gpio)] = FlowMeterData()
        except Exception as e:
            print e

    def get_unit(self):
        unit = cbpi.get_config_parameter("flowunit", None)
        if self.sensorShow == "Flow, unit/s":
            unit = unit + "/s"
        return unit

    def doAClick(self, channel):
        currentTime = int(time.time() * FlowMeterData.MS_IN_A_SECOND)
        hertzProp = self.hertzProp
        self.fms[int(self.gpio)].update(currentTime, float(hertzProp))

    def convert(self, inputFlow):
        unit = cbpi.get_config_parameter("flowunit", None)
        if unit == "gal(us)": 
            inputFlow = inputFlow * 0.264172052
        elif unit == "gal(uk)": 
            inputFlow = inputFlow * 0.219969157
        elif unit == "qt": 
            inputFlow = inputFlow * 1.056688
        else:
            pass
        if self.sensorShow == "Flow, unit/s":
            inputFlow = "{0:.2f}".format(inputFlow)
        else:
            inputFlow = "{0:.2f}".format(inputFlow)
        return inputFlow

    def read(self):
        if self.sensorShow == "Total volume":
            flow = self.fms[int(self.gpio)].pour
            flowConverted = self.convert(flow)
            self.data_received(flowConverted)
        elif self.sensorShow == "Flow, unit/s":
            flow = self.fms[int(self.gpio)].flow
            flowConverted = self.convert(flow)
            self.data_received(flowConverted)
        else:
            print "error"

    def getValue(self):
        flow = self.fms[int(self.gpio)].pour
        flowConverted = self.convert(flow)
        return flowConverted

    def reset(self):
        self.fms[int(self.gpio)].clear()
        return "Ok"

    @cbpi.action("Reset to zero")
    def resetButton(self):
        self.reset()


@blueprint.route('/<id>/reset', methods=['GET'])
def reset_sensor_value(idt):
    for key, value in cbpi.cache.get("sensors").iteritems():
        if key == int(idt):
            if value.type == "Flowmeter":
                flowReset = value.instance.reset()
                return flowReset
            else:
                return "Sensor is not a Flowmeter"
        else:
            return "Sensor not found"


@blueprint.route('/<id>', methods=['GET'])
def get_sensor_value(idt):
    for key, value in cbpi.cache.get("sensors").iteritems():
        if key == int(idt):
            if value.type == "Flowmeter":
                flowValue = value.instance.getValue()
                return flowValue
            else:
                return "Sensor is not a Flowmeter"
        else:
            return "Sensor not found"


@blueprint.route('/list_all_sensors', methods=['GET'])
def list_all_sensors():
    output = []
    for key, value in cbpi.cache.get("sensors").iteritems():
        output.append({"id": key, "name": value.name, "type": value.type})
    return json.dumps(output)


@cbpi.step
class Flowmeter(StepBase):
    sensor = StepProperty.Sensor("Sensor")
    actorA = StepProperty.Actor("Actor 1")
    actorB = StepProperty.Actor("Actor 2")
    volume = Property.Number("Volume", configurable=True)
    resetFlowmeter = Property.Number("Reset flowmeter when done. 1 = Yes 0 = No", configurable=True, default_value="1")

    def init(self):
        if self.actorA is not None:
            self.actor_on(self.actorA)
        if self.actorB is not None:
            self.actor_on(self.actorB)   

    @cbpi.action("Turn Actor OFF")
    def start(self):
        if self.actorA is not None:
            self.actor_off(self.actorA)
        if self.actorB is not None:
            self.actor_off(self.actorB)   

    def reset(self):
        if self.actorA is not None:
            self.actor_off(self.actorA)
        if self.actorB is not None:
            self.actor_off(self.actorB)   

    def finish(self):
        if self.actorA is not None:
            self.actor_off(self.actorA)
        if self.actorB is not None:
            self.actor_off(self.actorB)   
        if self.resetFlowmeter == "1":
            cbpi.cache.get("sensors").get(int(self.sensor)).instance.reset()

    def execute(self):
        sensorValue = cbpi.cache.get("sensors").get(int(self.sensor)).instance.getValue()
        if sensorValue >= self.volume:
            self.next()


@cbpi.initalizer()
def init(cbpi):
    print "INITIALIZE FlOWMETER SENSOR,ACTOR AND STEP MODULE"
    cbpi.app.register_blueprint(blueprint, url_prefix='/api/flowmeter')
    print "READY"

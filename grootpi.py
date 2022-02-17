from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import time
import argparse
import json
import RPi.GPIO as GPIO
import smbus
import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn
import adafruit_dht

endpoint = "xxxxxxxxxxxxxx-ats.iot.eu-central-1.amazonaws.com"
root = "certificate/AmazonRootCA1.pem"
certificate = "certificate/certificate.pem.crt"
private = "certificate/private.pem.key"
port = 8883

dhtDevice = adafruit_dht.DHT11(board.D4, use_pulseio=False)

spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
cs = digitalio.DigitalInOut(board.D5)
mcp = MCP.MCP3008(spi, cs)
channel = AnalogIn(mcp, MCP.P0)

DEVICE     = 0x23 # Default device I2C address

POWER_DOWN = 0x00 # No active state
POWER_ON   = 0x01 # Power on
RESET      = 0x07 # Reset data register value
# Start measurement at 4lx resolution. Time typically 16ms.
CONTINUOUS_LOW_RES_MODE = 0x13
# Start measurement at 1lx resolution. Time typically 120ms
CONTINUOUS_HIGH_RES_MODE_1 = 0x10
# Start measurement at 0.5lx resolution. Time typically 120ms
CONTINUOUS_HIGH_RES_MODE_2 = 0x11
# Start measurement at 1lx resolution. Time typically 120ms
# Device is automatically set to Power Down after measurement.
ONE_TIME_HIGH_RES_MODE_1 = 0x20
# Start measurement at 0.5lx resolution. Time typically 120ms
# Device is automatically set to Power Down after measurement.
ONE_TIME_HIGH_RES_MODE_2 = 0x21
# Start measurement at 1lx resolution. Time typically 120ms
# Device is automatically set to Power Down after measurement.
ONE_TIME_LOW_RES_MODE = 0x23

#bus = smbus.SMBus(0) # Rev 1 Pi uses 0
bus = smbus.SMBus(1)  # Rev 2 Pi uses 1

RELAIS_1_GPIO = 22
GPIO.setup(RELAIS_1_GPIO, GPIO.OUT) # GPIO Assign mode
RELAIS_2_GPIO = 27
GPIO.setup(RELAIS_2_GPIO, GPIO.OUT) # GPIO Assign mode
RELAIS_3_GPIO = 17
GPIO.setup(RELAIS_3_GPIO, GPIO.OUT) # GPIO Assign mode

def convertToNumber(data):
  # Simple function to convert 2 bytes of data
  # into a decimal number. Optional parameter 'decimals'
  # will round to specified number of decimal places.
  result=(data[1] + (256 * data[0])) / 1.2
  return (result)

def getLight(addr=DEVICE):
  # Read data from I2C interface
  data = bus.read_i2c_block_data(addr,ONE_TIME_HIGH_RES_MODE_1)
  return convertToNumber(data)

def lightPlant(lightlevel, light_desired, lightlimit):
  if light_desired == "on":
    GPIO.output(RELAIS_1_GPIO, GPIO.LOW) # on
    light_reported = "on"
  elif light_desired == "off":
    GPIO.output(RELAIS_1_GPIO, GPIO.HIGH) # off
    if lightlevel <= lightlimit:
      #print(" No light, Can you please enlight me")
      GPIO.output(RELAIS_1_GPIO, GPIO.LOW) # on
      light_reported = "on"
    elif lightlevel > lightlimit:
      GPIO.output(RELAIS_1_GPIO, GPIO.HIGH) # on
      #print(" Stop burning me!")
      light_reported = "off"
  time.sleep(1.5)
  return(light_reported)

def getMoisture():
  moisture = channel.value # Get the analog reading from the soil moist sensor
  moisture = 100 - (moisture * 100 / 65536) # Converting the moisture value to percentage
  return(moisture)

def wateringPlant(moisture, waterpump_desired, moisturelimit):
  if waterpump_desired == "on":
    GPIO.output(RELAIS_2_GPIO, GPIO.LOW) # on
    waterpump_reported = "on"
  elif waterpump_desired == "off":
    GPIO.output(RELAIS_2_GPIO, GPIO.HIGH) # off
    if moisture <= moisturelimit:
      #print(" No water, Can you please water me")
      GPIO.output(RELAIS_2_GPIO, GPIO.LOW) # on
      waterpump_reported = "on"
    elif moisture > moisturelimit:
      GPIO.output(RELAIS_2_GPIO, GPIO.HIGH) # on
      #print(" Stop drowning me!")
      waterpump_reported = "off"
  time.sleep(1.5)
  return(waterpump_reported)

def getDHTdata():
  temperature = dhtDevice.temperature
  humidity = dhtDevice.humidity
  return(temperature, humidity)

def ventPlant(temperature, ventilation_desired, temperaturelimit):
  if ventilation_desired == "on":
    GPIO.output(RELAIS_3_GPIO, GPIO.LOW) # on
    ventilation_reported = "on"
  elif ventilation_desired == "off":
    GPIO.output(RELAIS_3_GPIO, GPIO.HIGH) # off
    if temperature >= temperaturelimit:
      #print(" No fresh air, Can you please blow on me")
      GPIO.output(RELAIS_3_GPIO, GPIO.LOW) # on
      ventilation_reported = "on"
    elif temperature < temperaturelimit:
      GPIO.output(RELAIS_3_GPIO, GPIO.HIGH) # on
      #print(" Stop blowing on me!")
      ventilation_reported = "off"
  time.sleep(1.5)
  return(ventilation_reported)

def getserial():
  # Extract serial from cpuinfo file
  cpuserial = "0000000000000000"
  try:
    f = open('/proc/cpuinfo','r')
    for line in f:
      if line[0:6]=='Serial':
        cpuserial = line[10:26]
    f.close()
  except:
    cpuserial = "ERROR000000000"
  return cpuserial

def customCallback(client, userdata, message):
    global payload
    payload = json.loads(message.payload)

myAWSIoTMQTTClient = AWSIoTMQTTClient("")
myAWSIoTMQTTClient.configureEndpoint(endpoint, port)
myAWSIoTMQTTClient.configureCredentials(root, private, certificate)

# AWSIoTMQTTClient connection configuration
myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
myAWSIoTMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)  # 5 sec

# Connect and subscribe to AWS IoT
myAWSIoTMQTTClient.connect()
myAWSIoTMQTTClient.subscribe("$aws/things/blevk-prod-grootbot-thing/shadow/name/GrootShadow/get/#", 1, customCallback)
myAWSIoTMQTTClient.publish("$aws/things/blevk-prod-grootbot-thing/shadow/name/GrootShadow/get", "", 1)
time.sleep(1)

if payload == {'code': 404, 'message': "No shadow exists with name: 'blevk-prod-grootbot-thing~GrootShadow'"}:
    init_shadow = {
    "state": {
        "desired": {
            "light": "off",
            "waterpump":  "off",
            "ventilation": "off",
            "temperaturelimit": 0,
            "lightlimit": 0,
            "humiditylimit": 0,
            "moisturelimit": 0
            },
        "reported": {
            "light": "off",
            "waterpump":  "off",
            "ventilation": "off",
            "temperaturelimit": 0,
            "lightlimit": 0,
            "humiditylimit": 0,
            "moisturelimit": 0
            }
        }
    }
    myAWSIoTMQTTClient.publish("$aws/things/blevk-prod-grootbot-thing/shadow/name/GrootShadow/update", json.dumps(init_shadow), 1)
    print("Shadow was created")
else:
    # Get all variables
    desired = payload["state"]["desired"]
    light_desired = desired["light"]
    waterpump_desired = desired["waterpump"]
    ventilation_desired = desired["ventilation"]
    temperaturelimit = int(desired["temperaturelimit"])
    lightlimit = int(desired["lightlimit"])
    humiditylimit = int(desired["humiditylimit"])
    moisturelimit = int(desired["moisturelimit"])
    serialnumber = getserial()
    # Get sensor data
    while True:
      try:
        DHT_data = getDHTdata()
        temperature = round(DHT_data[0])
        humidity = round(DHT_data[1])
        lightlevel = round(getLight())
        moisture = round(getMoisture())
      except:
        continue
      break
    #Turn stuff omyAWSIoTMQTTClientn/off regarding to logic
    light_reported = lightPlant(lightlevel, light_desired, lightlimit)
    waterpump_reported = wateringPlant(moisture, waterpump_desired, moisturelimit)
    ventilation_reported = ventPlant(temperature, ventilation_desired, temperaturelimit)
    # DEBUG
    print("desired: ", desired)
    print("DHT_data: ", DHT_data)
    print("temperature: ", temperature)
    print("humidity: ", humidity)
    print("lightlevel: ", lightlevel)
    print("moisture: ", moisture)
    print("light_reported: ", light_reported)
    print("waterpump_reported: ", waterpump_reported)
    print("ventilation_reported: ", ventilation_reported)
    # Send reported state and sensors data
    reported = {
    "state": {
          "reported": {
            "light": light_reported,
            "waterpump":  waterpump_reported,
            "ventilation": ventilation_reported,
            "temperaturelimit": temperaturelimit,
            "lightlimit": lightlimit,
            "humiditylimit": humiditylimit,
            "moisturelimit": moisturelimit
          }
        }
    }
    sensors = {
      "SerialNumber": serialnumber,
      "Humidity": humidity,
      "Light": lightlevel,
      "Moisture": moisture,
      "Temperature": temperature
    }
    myAWSIoTMQTTClient.publish("grootbot/sensors", json.dumps(sensors), 1)
    myAWSIoTMQTTClient.publish("$aws/things/blevk-prod-grootbot-thing/shadow/name/GrootShadow/update", json.dumps(reported), 1)
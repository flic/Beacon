#! /usr/bin/env python
# -*- coding: utf-8 -*-

import string,cgi,time
from os import curdir, sep
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn
from urlparse import urlparse
from cgi import parse_qs
import simplejson as json
import threading
import fnmatch

def updateVar(name, value):
	if name not in indigo.variables:
		indigo.variable.create(name, value=value)
	else:
		indigo.variable.updateValue(name, value)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""

class httpHandler(BaseHTTPRequestHandler):
   def __init__(self, plugin,*args):
      self.plugin = plugin
      self.plugin.debugLog(u"New httpHandler thread: "+threading.currentThread().getName()+", total threads: "+str(threading.activeCount()))
      BaseHTTPRequestHandler.__init__(self,*args)
    
   def deviceUpdate(self,device,deviceAddress,event):
      self.plugin.debugLog(u"deviceUpdate called")

      if (self.plugin.createVar):
         updateVar("Beacon_deviceID",str(device.id))
         updateVar("Beacon_name",deviceAddress.split('@@')[0])
         updateVar("Beacon_location",deviceAddress.split('@@')[1])
      
      if event == "LocationEnter" or event == "enter" or event == "1":
         indigo.server.log("Enter location notification received from sender/location "+deviceAddress)
         device.updateStateOnServer("onOffState", True)
         device.updateStateImageOnServer(indigo.kStateImageSel.MotionSensorTripped)
         self.triggerEvent("statePresent",deviceAddress)
      elif event == "LocationExit" or event == "exit" or event == "0":
         indigo.server.log("Exit location notification received from sender/location "+deviceAddress)
         device.updateStateOnServer("onOffState", False)
         device.updateStateImageOnServer(indigo.kStateImageSel.MotionSensor)
         self.triggerEvent("stateAbsent",deviceAddress)
      elif event == "LocationTest" or event=="test":
         indigo.server.log("Test location notification received from sender/location "+deviceAddress)
      self.triggerEvent("stateChange",deviceAddress)
            
   def triggerEvent(self,eventType,deviceAddress):
      self.plugin.debugLog(u"triggerEvent called")
      for trigger in self.plugin.events[eventType]:
         if (self.plugin.events[eventType][trigger].pluginProps["manualAddress"]):
            indigo.trigger.execute(trigger)
         elif (fnmatch.fnmatch(deviceAddress.lower(),self.plugin.events[eventType][trigger].pluginProps["deviceAddress"].lower())):
            indigo.trigger.execute(trigger)
         
   def deviceCreate(self,sender,location):
      self.plugin.debugLog(u"deviceCreate called")
      deviceName = sender+"@@"+location
      device = indigo.device.create(address=deviceName,deviceTypeId="beacon",name=deviceName,protocol=indigo.kProtocol.Plugin)
      self.plugin.debugLog(u"Created new device, "+ deviceName)
      device.updateStateOnServer("onOffState",False)
      device.updateStateImageOnServer(indigo.kStateImageSel.MotionSensor)
      return device.id
 
   def parseResult(self,sender,location,event):
      self.plugin.debugLog(u"parseResult called")
      deviceAddress = sender.lower()+"@@"+location.lower()
      foundDevice = False         
      if self.plugin.deviceList:
         for b in self.plugin.deviceList:
            if (self.plugin.deviceList[b]['address'] == deviceAddress):
               self.plugin.debugLog(u"Found userLocation device: " + self.plugin.deviceList[b]['name'])
               self.deviceUpdate(self.plugin.deviceList[b]['ref'],deviceAddress,event)
               foundDevice = True
      if foundDevice == False:
         self.plugin.debugLog(u"No device found")
         indigo.server.log("Received "+event+" from "+deviceAddress+" but no corresponding device exists",isError=True)
         if self.plugin.createDevice:
            newdev = self.deviceCreate(sender,location)
            self.deviceUpdate(self.plugin.deviceList[newdev]['ref'],deviceAddress,event)

   def do_POST(self):
      global rootnode
      foundDevice = False
      self.plugin.debugLog(u"Received HTTP POST")
      self.plugin.debugLog(u"Sending HTTP 200 response")
      self.send_response(200)
      self.end_headers()

      try:
         ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
         uagent = str(self.headers.getheader('user-agent'))
         self.plugin.debugLog(u"User-agent: %s, Content-type: %s" % (uagent, ctype))
         data = self.rfile.read(int(self.headers['Content-Length']))
         data = data.decode('utf-8') 
         self.plugin.debugLog(u"Data (UTF-8 decoded):  %s" % data)
# Locative
         if (('Geofancy' in uagent) or ('Locative' in uagent)):
            self.plugin.debugLog(u"Recognised Locative ")
            if (self.plugin.geofancy):
               if (ctype == 'application/x-www-form-urlencoded'):
                  pdata = parse_qs(data)
                  p = {}
                  for key, value in pdata.iteritems():
                     p.update({key:value[0]})            
                  if all(name in data for name in ('device','id','trigger')):
                     self.parseResult(p["device"],p["id"],p["trigger"])
                  else:
                     indigo.server.log(u"Received Locative data, but one or more parameters are missing",isError=True)
               else:
                   indigo.server.log(u"Recognised Locative, but received data was wrong content-type: %s" % ctype,isError=True)
            else:
               indigo.server.log(u"Received Locative data, but Locative is disabled in plugin config")
# Geofency
         elif ('Geofency' in uagent):
            self.plugin.debugLog(u"Recognised Geofency")
            if (self.plugin.geofency):
               if (ctype == 'application/json'):
                  p = json.loads(data)
                  if all(name in data for name in ('name','entry','device')):
                     self.parseResult(p["device"],p["name"],p["entry"])
                  else:
                     indigo.server.log(u"Received Geofency data, but one or more parameters are missing",isError=True)
               else:
                  indigo.server.log(u"Recognised Geofency, but received data was wrong content-type: %s" % ctype,isError=True)
            else:
               indigo.server.log(u"Received Geofency data, but Geofency is disabled in plugin config")
#Beecon
         elif ('Beecon' in uagent):
            self.plugin.debugLog(u"Recognised Beecon")
            if (self.plugin.beecon):
               pdata = parse_qs(data)
               p = {}
               for key, value in pdata.iteritems():
                  p.update({key:value[0]})
               if all(name in data for name in ('region','action')):
                  self.parseResult("Beecon",p["region"],p["action"])
               else:
                  indigo.server.log(u"Received Beecon data, but one or more parameters are missing",isError=True)
            else:
               indigo.server.log(u"Received Beecon data, but Beecon is disabled in plugin config")
# Geohopper
         elif ctype == 'application/json': 
            self.plugin.debugLog(u"Received JSON data (possible Geohopper)")
            if (self.plugin.geohopper):
               p = json.loads(data)
               if all(name in data for name in ('sender','location','event')):
                  self.parseResult(p["sender"],p["location"],p["event"])
               else:
                  indigo.server.log(u"Received Geohopper data, but one or more parameters are missing",isError=True)
            else:
                indigo.server.log(u"Received Geohopper data, but Geohopper is disabled in plugin config")
         else:
            indigo.server.log(u"Didn't recognise received data. (User-agent: %s, Content-type: %s)" % (uagent, ctype),isError=True)
      except Exception as e:
         indigo.server.log(u"Exception: %s" % str(e), isError=True)
         pass

class Plugin(indigo.PluginBase):
   def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
      indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
      self.deviceList = {}
      
      self.events = dict()
      self.events["stateChange"] = dict()
      self.events["statePresent"] = dict()
      self.events["stateAbsent"] = dict()
      
   def __del__(self):
      indigo.PluginBase.__del__(self)
    
   def startup(self):
      self.loadPluginPrefs()
      self.debugLog(u"Startup called")
      self.myThread = threading.Thread(target=self.listenHTTP, args=())
      self.myThread.daemon = True
      self.myThread.start()

   def deviceCreated(self, device):
      self.debugLog(device.name + ": Created device of type \"%s\"" % device.deviceTypeId)
      self.deviceList[device.id] = {'ref':device,'name':device.name,'address':device.address.lower()}

   def deviceStartComm(self, device):
      self.debugLog(device.name + ": Starting device")
      if (device.deviceTypeId == u'userLocation'):
         indigo.server.log("Device "+device.name+" needs to be deleted and recreated.",isError=True)
      else:
         self.deviceList[device.id] = {'ref':device,'name':device.name,'address':device.address.lower()}

   def deviceStopComm(self, device):
      self.debugLog(device.name + ": Stopping device")
      if (device.deviceTypeId == u'beacon'):
         del self.deviceList[device.id]

   def shutdown(self):
      self.debugLog(u"Shutdown called")

   def triggerStartProcessing(self, trigger):
      self.debugLog(u"Start processing trigger " + unicode(trigger.name))
      self.events[trigger.pluginTypeId][trigger.id] = trigger

   def triggerStopProcessing(self, trigger):
      self.debugLog(u"Stop processing trigger " + unicode(trigger.name))
      if trigger.pluginTypeId in self.events:
         if trigger.id in self.events[trigger.pluginTypeId]:
            del self.events[trigger.pluginTypeId][trigger.id]

   def actionControlSensor(self, action, device):
      self.debugLog(u"Manual sensor state change request: " + device.name)
      if device.pluginProps['AllowOnStateChange']:
         if action.sensorAction == indigo.kSensorAction.TurnOn:
			device.updateStateOnServer("onOffState", True)
			device.updateStateImageOnServer(indigo.kStateImageSel.MotionSensorTripped)
         elif action.sensorAction == indigo.kSensorAction.TurnOff:
            device.updateStateOnServer("onOffState", False)
            device.updateStateImageOnServer(indigo.kStateImageSel.MotionSensor)
         elif action.sensorAction == indigo.kSensorAction.Toggle:
            device.updateStateOnServer("onOffState", not device.onState)
            if (device.onState):
               device.updateStateImageOnServer(indigo.kStateImageSel.MotionSensorTripped)
            else:
               device.updateStateImageOnServer(indigo.kStateImageSel.MotionSensor)
      else:
         self.debugLog(u"ignored request (sensor is read-only)")

   def validatePrefsConfigUi(self, valuesDict):	
      self.debugLog(u"validating Prefs called")	
      port = int(valuesDict[u'listenPort'])	
      if (port <= 0 or port>65535):
         errorMsgDict = indigo.Dict()
         errorMsgDict[u'port'] = u"Port number needs to be a valid TCP port (1-65535)."
         return (False, valuesDict, errorMsgDict)
      return (True, valuesDict)

   def closedPrefsConfigUi ( self, valuesDict, UserCancelled):
      if UserCancelled is False:
         indigo.server.log ("Preferences were updated.")
         if not (self.listenPort == int(self.pluginPrefs['listenPort'])):
            indigo.server.log("New listen port configured, reload plugin for change to take effect",isError=True)
         self.loadPluginPrefs()

   def loadPluginPrefs(self):
      self.debugLog(u"loadpluginPrefs called")	
      self.debug = self.pluginPrefs.get('debugEnabled',False)
      self.createDevice = self.pluginPrefs.get('createDevice',True)
      self.listenPort = int(self.pluginPrefs.get('listenPort',6192))
      self.beecon = self.pluginPrefs.get('beecon',True)
      self.geofancy = self.pluginPrefs.get('geofancy',True)
      self.geohopper = self.pluginPrefs.get('geohopper',True)
      self.geofency = self.pluginPrefs.get('geofency',True)
      self.createVar = self.pluginPrefs.get('createVar',False)

   def listenHTTP(self):
      self.debugLog(u"Starting HTTP listener thread")
      indigo.server.log(u"Listening on TCP port " + str(self.listenPort))
      self.server = ThreadedHTTPServer(('', self.listenPort), lambda *args: httpHandler(self, *args))
      self.server.serve_forever()
            
   def runConcurrentThread(self):
      while True:
         self.sleep(1)
         

 

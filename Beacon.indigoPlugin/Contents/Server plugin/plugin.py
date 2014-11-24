#! /usr/bin/env python
# -*- coding: utf-8 -*-

import string,cgi,time
from os import curdir, sep
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from urlparse import urlparse
from cgi import parse_qs
import simplejson as json
import threading

class httpHandler(BaseHTTPRequestHandler):
   def __init__(self, plugin,*args):
      self.plugin = plugin
      BaseHTTPRequestHandler.__init__(self,*args)
    
   def deviceUpdate(self,device,sender,location,event):
      self.plugin.debugLog(u"deviceUpdate called")
      if event == "LocationEnter" or event == "enter" or event == "1":
         indigo.server.log("Enter location notification received from sender/location "+sender+"//"+location)
         device.updateStateOnServer(key="state",value="present")
         for trigger in self.plugin.events["statePresent"]:
            indigo.trigger.execute(trigger)
      elif event == "LocationExit" or event == "exit" or event == "0":
         indigo.server.log("Exit location notification received from sender/location "+sender+"//"+location)
         device.updateStateOnServer(key="state",value="absent")
         for trigger in self.plugin.events["stateAbsent"]:
            indigo.trigger.execute(trigger)
      elif event == "LocationTest" or event=="test":
         indigo.server.log("Test location notification received from sender/location "+sender+"//"+location)
      for trigger in self.plugin.events["stateChange"]:
         indigo.trigger.execute(trigger)
         
   def deviceCreate(self,sender,location):
      self.plugin.debugLog(u"deviceCreate called")
      deviceName = sender+"//"+location
      device = indigo.device.create(address=sender,deviceTypeId="userLocation",name=deviceName,protocol=indigo.kProtocol.Plugin,props={"location":location})
      self.plugin.debugLog(u"Created new device, "+ deviceName)
      device.updateStateOnServer(key="state",value="unknown")
      self.plugin.deviceList[device.id] = {'ref':device,'name':device.name,'address':device.address.lower(),'location':device.pluginProps['location'].lower()}
      return device.id

   def sanityCheck(self,data,check):
      self.plugin.debugLog(u"sanityCheck called")
      try:
         if all(name in data for name in check):
            self.plugin.debugLog(u"Data passed sanityCheck")
            return True
         else:
            self.plugin.debugLog(u"Data failed sanityCheck")
            return False
      except:
         self.plugin.debugLog(u"Exception occured in sanityCheck")
         return false
 
   def parseResult(self,sender,location,event):
      self.plugin.debugLog(u"parseResult called")
      foundDevice = False         
      if self.plugin.deviceList:
         for b in self.plugin.deviceList:
            if (self.plugin.deviceList[b]['address'] == sender.lower()) and (self.plugin.deviceList[b]['location'] == location.lower()):
               self.plugin.debugLog(u"Found userLocation device: " + self.plugin.deviceList[b]['name'])
               self.deviceUpdate(self.plugin.deviceList[b]['ref'],sender,location,event)
               foundDevice = True
      if foundDevice == False:
         self.plugin.debugLog(u"No device found")
         indigo.server.log("Received "+event+" from "+sender+"//"+location+" but no corresponding device exists",isError=True)
         if self.plugin.createDevice:
            newdev = self.deviceCreate(sender,location)
            self.deviceUpdate(self.plugin.deviceList[newdev]['ref'],sender,location,event)

   def parseGeofancy(self,data):
      self.plugin.debugLog(u"parseGeofancy called")
      pdata = parse_qs(data)
      p = {}
      for key, value in pdata.iteritems():
         p.update({key:value[0]})
      if self.sanityCheck(p,self.plugin.geofancy_params):
         self.parseResult(p["device"],p["id"],p["trigger"])

   def parseGeohopper(self,data):
      self.plugin.debugLog(u"parseGeohopper called")
      p = json.loads(data)
      if self.sanityCheck(p,self.plugin.geohopper_params):
         self.parseResult(p["sender"],p["location"],p["event"])

   def parseGeofency(self,data):
      self.plugin.debugLog(u"parseGeofency called")
      p = json.loads(data)
      if self.sanityCheck(p,self.plugin.geofency_params):
         self.parseResult(p["device"],p["name"],p["entry"])
  
   def parseBeecon(self,data):  
      self.plugin.debugLog(u"parseBeecon called")
      pdata = parse_qs(data)
      p = {}
      for key, value in pdata.iteritems():
         p.update({key:value[0]})
      if self.sanityCheck(p,self.plugin.beecon_params):
         self.parseResult("Beecon",p["region"],p["action"])

   def do_POST(self):
      global rootnode
      foundDevice = False
      self.plugin.debugLog(u"Received HTTP POST")
      try:
         ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
         uagent = str(self.headers.getheader('user-agent'))
         self.plugin.debugLog(u"User-agent: " + uagent)
         if ('Geofancy' in uagent) and ctype == 'application/x-www-form-urlencoded' and self.plugin.geofancy:
            data = self.rfile.read(int(self.headers['Content-Length']))
            self.plugin.debugLog(u"Received Geofancy data: " + str(data))
            self.parseGeofancy(data)
         elif ('Geofency' in uagent) and ctype == 'application/json' and self.plugin.geofency:
            data = self.rfile.read(int(self.headers['Content-Length']))
            self.plugin.debugLog(u"Received Geofency data: " + str(data))
            self.parseGeofency(data)
         elif ('Beecon' in uagent) and self.plugin.beecon:
            data = self.rfile.read(int(self.headers['Content-Length']))
            self.plugin.debugLog(u"Received Beecon data: " + str(data))
            self.parseBeecon(data)
         elif ctype == 'application/json' and self.plugin.geohopper: 
            data = self.rfile.read(int(self.headers['Content-Length']))
            self.plugin.debugLog(u"Received JSON data: " + str(data))
            self.parseGeohopper(data)
      except:
         pass
         
      self.plugin.debugLog(u"Sending HTTP 200 response")
      self.send_response(200)
      self.end_headers()

class Plugin(indigo.PluginBase):
   def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
      indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
      self.deviceList = {}
      self.geohopper_params = ('sender','location','event')
      self.geofancy_params = ('device','id','latitude','longitude','timestamp','trigger')
      self.geofency_params = ('id','name','entry','date','latitude','longitude','device')
      self.beecon_params = ('region','action')
      
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
      self.debugLog(u"Created device of type \"%s\"" % device.deviceTypeId)

   def deviceStartComm(self, device):
      self.debugLog(device.name + ": Starting device")
      self.deviceList[device.id] = {'ref':device,'name':device.name,'address':device.address.lower(),'location':device.pluginProps['location'].lower()}

   def deviceStopComm(self, device):
      self.debugLog(device.name + ": Stopping device")
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

   def listenHTTP(self):
      self.debugLog(u"Starting HTTP listener thread")
      indigo.server.log(u"Listening on TCP port " + str(self.listenPort))
      self.server = HTTPServer(('', self.listenPort), lambda *args: httpHandler(self, *args))
      self.server.serve_forever()
      
   def runConcurrentThread(self):
      while True:
         self.sleep(1)
         

 

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
      if event == "LocationEnter" or event == "enter":
         indigo.server.log("Enter location notification received from sender/location "+sender+"//"+location)
         device.updateStateOnServer(key="state",value="present")
      elif event == "LocationExit" or event == "exit":
         indigo.server.log("Exit location notification received from sender/location "+sender+"//"+location)
         device.updateStateOnServer(key="state",value="absent")
      elif event == "LocationTest" or event=="test":
         indigo.server.log("Test location notification received from sender/location "+sender+"//"+location)
         
   def deviceCreate(self,sender,location):
      self.plugin.debugLog(u"deviceCreate called")
      deviceName = sender+"//"+location
      device = indigo.device.create(address=sender,deviceTypeId="userLocation",name=deviceName,protocol=indigo.kProtocol.Plugin,props={"location":location})
      self.plugin.debugLog(u"Created new device, "+ deviceName)
      device.updateStateOnServer(key="state",value="unknown")
      self.plugin.deviceList[device.id] = {'ref':device,'name':device.name,'address':device.address,'location':device.pluginProps['location'].lower()}
      return device

   def sanityCheck_geohopper(self,data):
      self.plugin.debugLog(u"sanityCheck_geohopper called")
      try:
         if all(name in data for name in self.plugin.geohopper_params):
            self.plugin.debugLog(u"Data passed Geohopper sanityCheck")
            return True
         else:
            self.plugin.debugLog(u"Data failed Geohopper sanityCheck")
            return False
      except:
         self.plugin.debugLog(u"Exception occured in Geohopper sanityCheck")
         return false

   def sanityCheck_geofancy(self,data):
      self.plugin.debugLog(u"sanityCheck_geofancy called")
      try:
         if all(name in data for name in self.plugin.geofancy_params_params):
            self.plugin.debugLog(u"Data passed Geofancy sanityCheck")
            return True
         else:
            self.plugin.debugLog(u"Data failed Geofancy sanityCheck")
            return False
      except:
         self.plugin.debugLog(u"Exception occured in Geofancy sanityCheck")
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
            self.deviceUpdate(newdev,data)

   def parseGeofancy(self,data):
      self.plugin.debugLog(u"parseGeofancy called")
      pdata = parse_qs(data)
      p = {}
      for key, value in pdata.iteritems():
         p.update({key:value[0]})
      if self.sanityCheck_geofancy:
         self.parseResult(p["device"],p["id"],p["trigger"])

   def parseGeohopper(self,data):
      self.plugin.debugLog(u"parseGeohopper called")
      p = json.loads(data)
      if self.sanityCheck_geohopper(p):
         self.parseResult(p["sender"],p["location"],p["event"])
  
   def parseBeecon(data):  
      self.plugin.debugLog(u"parseBeecon called")
      p = {}
      for key, value in data.iteritems() :
         p.update({key:value[0]})
      if self.sanityCheck_geohopper(p):   
         self.parseResult(p["sender"],p["location"],p["event"])

   def do_POST(self):
      global rootnode
      foundDevice = False
      self.plugin.debugLog(u"Received HTTP POST")
      try:
         ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
         uagent = str(self.headers.getheader('user-agent'))
         self.plugin.debugLog(u"User-agent: " + uagent)
         if uagent.find('geofancy') and ctype == 'application/x-www-form-urlencoded' and self.plugin.geofancy:
            data = self.rfile.read(int(self.headers['Content-Length']))
            self.plugin.debugLog(u"Received Geofancy data: " + str(data))
            self.parseGeofancy(data)

         if ctype == 'application/json' and self.plugin.geohopper: 
            data = self.rfile.read(int(self.headers['Content-Length']))
            self.plugin.debugLog(u"Received JSON data: " + str(data))
            self.parseGeohopper(data)
         self.send_response(200)
         self.end_headers()
      except:
         pass

   def do_GET(self):
      self.plugin.debugLog(u"Received HTTP GET")
      uagent = str(self.headers.getheader('user-agent'))
      self.plugin.debugLog(u"User-agent: " + uagent)
      parsed_path = urlparse(self.path)
      if uagent.find('geofancy') and self.plugin.geofancy:
         self.plugin.debugLog(u"Received Geofancy data: " + str(parsed_path))
         self.parseGeofancy(data)
      elif self.plugin.httpGet:
         self.plugin.debugLog(u"Received other HTTP GET data: " + str(parsed_path))
         data = parse_qs(parsed_path.query)
         self.parseBeecon(data)
      self.send_response(200)
      self.end_headers()

class Plugin(indigo.PluginBase):
   def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
      indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
      self.deviceList = {}
      self.geohopper_params = ('sender','location','event')
      self.geofancy_params = ('device','id','latitude','longitude','timestamp','trigger')

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
      self.deviceList[device.id] = {'ref':device,'name':device.name,'address':device.address,'location':device.pluginProps['location'].lower()}

   def deviceStopComm(self, device):
      self.debugLog(device.name + ": Stopping device")
      del self.deviceList[device.id]

   def shutdown(self):
      self.debugLog(u"Shutdown called")

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
      self.httpGet = self.pluginPrefs.get('httpGet',True)
      self.geofancy = self.pluginPrefs.get('geofancy',True)
      self.geohopper = self.pluginPrefs.get('geohopper',True)

   def listenHTTP(self):
      self.debugLog(u"Starting HTTP listener thread")
      indigo.server.log(u"Listening on TCP port " + str(self.listenPort))
      self.server = HTTPServer(('', self.listenPort), lambda *args: httpHandler(self, *args))
      self.server.serve_forever()
      
   def runConcurrentThread(self):
      while True:
         self.sleep(1)
         

 

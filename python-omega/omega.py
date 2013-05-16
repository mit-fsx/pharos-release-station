import sys
import warnings
import logging
import uuid
import time
from suds import WebFault
from suds.client import Client
from suds.plugin import MessagePlugin
from suds.sax.element import Element
from xml.dom.minidom import parseString
from xml.etree import ElementTree

# Set up a null logging handler to avoid
# "No handlers found" error
class NullHandler(logging.Handler):
    def emit(self, record):
        pass

# Sigh.  It's unclear if this is Microsoft's fault or Pharos' fault.
# Regardless, something cares about what the namespace is actually
# named vs what its URI is
class _FixupEnvelope(MessagePlugin):
    def marshalled(self, context):
        root = context.envelope.getRoot()
        envelope = root.getChild("Envelope")
        envelope.getChildren()[1].setPrefix("SOAP-ENV")

class OmegaException(Exception):
    pass

class PharosEDIException(OmegaException):
    # TODO: Get Pharos to fix the stupid script
    _noUserFound = "Script 'Alternative-Offline and Lock Fix': error after line 115: No user found matching: "

    def __init__(self, webFaultException):
        if webFaultException is not None:
            if not isinstance(webFaultException, WebFault):
                raise OmegaException('PharosEDIException arguments must be of type WebFault')
            self._fault = webFaultException.fault
            self.message = webFaultException.fault.faultstring
            if self._fault.faultcode == "Pedi.InternalError":
                self.message = self._fault.faultstring.replace("An internal server error occurred. ", "", 1)
                if self._noUserFound in self.message:
                    self.message = "User not found in Pharos database."
    
    def __repr__(self):
        return "%s: %s" % (self.__class__, self.message)

    def __str__(self):
        return "PharosEDIException: " + self.message
        


class PharosPrintJob:
    _basicAttrs = ('job_id', 'queue', 'jobname', 'when_submitted', 'username', 'protected')
    _extAttrs = ('pages', 'sheets', 'cost', 'job_attributes')

    def __init__(self, xmlElementTree=None):
        self.when_submitted = None
        self.job_id = None
        self.user = None
        self.protected = False
        self.title = None
        self.queue = None
        # Extended attributes
        self.pages = None
        self.sheets = None
        self.cost = None
        self.job_attributes = None
        self._struct_time = None

        if xmlElementTree is not None:
            self.__dict__.update(dict((x, xmlElementTree.find(x).text) for x in self._basicAttrs))

    def setDetails(self, details):
        self.__dict__.update(dict((x, details[x] if x in details else None) for x in self._extAttrs))

    def formattedDate(self, strformat):
        if self.when_submitted is None:
            return None
        if self._struct_time is None and self.when_submitted is not None:
            try:
                self._struct_time = time.strptime(self.when_submitted, "%Y/%m/%d %H:%M:%S")
                return time.strftime(strformat, self._struct_time)
            except ValueError:
                return None


class Omega:
    logger = logging.getLogger('Omega')
    _wsdlPath='/PharosEdi/EdiService.asmx?WSDL'

    def __init__(self, ediHost, useSSL=True, wsdlPath=_wsdlPath, debugLevel=0):
        h = NullHandler()
        self.logger.addHandler(h)
        if debugLevel:
            self.logger.setLevel(logging.DEBUG)
            if debugLevel > 10:
                logging.getLogger('suds.client').setLevel(logging.DEBUG)
            if debugLevel > 100:
                logging.getLogger('suds.transport').setLevel(logging.DEBUG)
        if not '.' in ediHost:
            warnings.warn("ediHost (%s) is not a FQDN" % (ediHost))
        self.uri = ('https://' if useSSL else 'http://') + ediHost + wsdlPath
        self.session_id = None
        try:
            self.soapClient = Client(self.uri, plugins=[_FixupEnvelope()])
            self.soapClient.service.Online()
        except Exception as e:
            raise OmegaException(e)

    def _requireSession(self):
        if not self.session_id:
            raise OmegaException('No session.')

    def start_session(self, omega_name, site_password):
        try:
            result = self.soapClient.service.InitializeSession2(site_password)
        except WebFault as e:
            raise PharosEDIException(e)
        
        self.session_id = result.session_id
        self.tzinfo = (result.utc_time, result.utc_offset, result.time_zone_name)
        # Add the session ID to the header for future queries
        # TODO: Session expiration?  Sessions don't appear to expire if Ping()'d?
        # Or even if not Pinged?
        self.soapClient.set_options(soapheaders=Element('session_id').setText(self.session_id))
        try:
            station_config = self.soapClient.service.GetPharosStations2('', omega_name)
        except WebFault as e:
            raise PharosEDIException(e)
        self.omega_name = omega_name
        xml = ElementTree.XML(station_config)
        self.print_server = xml.find('pharos_station').get('print_server')
        # TODO: multiple printers?  Or sanity check count
        self.printer = xml.find('pharos_station').find('printers').find('printer').get('name')
        # Necessary for configuring session, otherwise 
        # you get a traceback "No billing bank has been assigned to this session"
        try:
            self.soapClient.service.ConfigureSession3(omega_name, '')
        except WebFault as e:
            raise PharosEDIException(e)
        # TODO: Ping?

    def connected(self):
        try:
            self.soapClient.service.Ping()
            return True
        except WebFault as e:
            if e.fault.faultstring == "The session is not running.":
                return False
            else:
                raise PharosEDIException(e)

    
    def get_version(self):
        try:
            version = self.soapClient.service.GetProductVersion()
        except WebFault as e:
            raise PharosEDIException(e)
        xml = ElementTree.XML(version)
        return tuple([xml.find(x).text for x in ('productname', 'majornumber', 'minornumber', 'buildnumber', 'edibuildnumber')])

    def getUsernameFromCard(self, cardId):
        try:
            result = self.soapClient.service.LoginUser(cardId, None)
        except WebFault as e:
            raise PharosEDIException(e)
        if result.access_level != "user":
            warnings.warn("access_level was not user.  That's weird.")
        return result.refer_id

    def getUserDetails(self, username, lockUser=True, transType=1):
        try:
            details = self.soapClient.service.GetUserDetails3(username, 1 if lockUser else 0, transType)
        except WebFault as e:
            raise PharosEDIException(e)
        return details

    def deleteJob(self, jobid, queue):
        try:
            self.soapClient.service.DeletePrintJob(self.print_server, queue, jobid)
        except WebFault as e:
            raise PharosEDIException(e)

    def unlockUser(self, username):
        try:
            self.soapClient.service.UnlockUser(username)
        except WebFault as e:
            raise PharosEDIException(e)

    def getUserPermissions(self, username):
        try:
            details = self.soapClient.service.GetUserPermissions(username, self.printer)
        except WebFault as e:
            raise PharosEDIException(e)
        return details

    def getPrintJobsForUser(self, username, objToUpdate=None):
        # WARNING: IT IS THE CALLERS RESPONSIBILITY TO AUTHENTICATE THE USER
        try:
            jobs = self.soapClient.service.ListPrintJobsForStation(self.print_server, self.omega_name, username)
        except WebFault as e:
            raise PharosEDIException(e)
        # TODO: Better Unicode support.
        jobsxml = ElementTree.XML(unicode(jobs).encode('ascii', errors='ignore'))
        jobslist = []
        for job in jobsxml.findall('print_job'):
            if callable(objToUpdate):
                objToUpdate()
            printjob = PharosPrintJob(job)
            try:
                details = self.soapClient.service.GetPrintJobDetails(self.print_server,
                                                                     printjob.queue, 
                                                                     printjob.job_id, 
                                                                     printjob.username)
                printjob.setDetails(details)
            except WebFault as e:
                pass
            jobslist.append(printjob)
        return jobslist
    
    def releaseJob(self, job_id, queue, username):
        try:
            result = self.soapClient.service.ReleaseAndRecordPrintJob3(str(uuid.uuid4()), self.print_server, queue, job_id, self.omega_name, username, None, None)
        except WebFault as e:
            raise PharosEDIException(e)
        return result


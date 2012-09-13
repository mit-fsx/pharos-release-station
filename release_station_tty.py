#!/usr/bin/python

import omega
import getpass
import sys
import os
import socket
from kpass import kpass, KpassError

SITE_PASS=''  #redacted
KSERVICE='daemon'

def authenticateUser():
    authenticated=False
    while not authenticated:
        username = raw_input('Username: ')
        rc=0
        try:
            rc = kpass(username, getpass.getpass(), 
                       KSERVICE, socket.getfqdn(), 
                       'FILE:'+os.path.dirname(sys.argv[0])+'/daemon.keytab')
        except KpassError, diag:
            print "krb5 error: %s" % str(diag)
        authenticated = (rc == 1)
        if rc != 1:
            print "Username/passsword incorrect."
            if raw_input('Try again? (y/n) ').lower() == 'n':
                sys.exit(1)
    return username
    


station = omega.Omega('pharos-prod.mit.edu')
while True:
    omeganame = raw_input('Emulate which omega? ')
    try: 
        station.start_session(omeganame, SITE_PASS)
        break
    except omega.PharosEDIException as e:
        print "Cannot emulate that omega: %s" % e.message
    
print "Connected to %s %s.%s (build %s, EDI build %s)" % station.get_version()
print "This omega controls printer %s on server %s" % (station.printer, station.print_server)
username = authenticateUser()
try:
    details = station.getUserDetails(username)
    print "Print quota balance: %d pages" % (int(details.balance * 10))
except omega.PharosEDIException as e:
    print "Could not retrieve user details: %s", e.message

try:
    joblist = station.getPrintJobsForUser(username)
except omega.PharosEDIException as e:
    print "Could not retrieve user print jobs: %s", e.message
    print "Exiting..."
    sys.exit(255)

if (len(joblist) == 0):
    print "No print jobs found.  Exiting..."
    sys.exit(0)

print '** Print Job Listing **'.center(80)
i=1
for job in joblist:
    print " %2d) (%d pages) %s    %s" % (i, job.pages, job.formattedDate("%b %m %H:%M"), job.jobname)
    i += 1
print ''

jobnum = raw_input("Release which job? ('0' to quit) ")
jobnum = int(jobnum)
if jobnum != 0:
    job = joblist[jobnum - 1]
    try:
        printer = station.releaseJob(job.job_id, job.queue, username)
        print "Job released to printer %s" % (printer)
    except omega.PharosEDIException as e:
        print "Error while releasing job:\n%s" % (e.message)

station.unlockUser(username)
sys.exit(0)    


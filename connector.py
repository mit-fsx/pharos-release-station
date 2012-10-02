#!/usr/bin/python

import sys
import os
import SocketServer
import omega

SOCKNAME="/var/run/pharosconn.sock"
SITEPASS='REDACTED'
OMEGA='wired-omega'

station = omega.Omega('pharos-prod.mit.edu')
try:
    station.start_session(OMEGA, SITEPASS)
except omega.PharosEDIException as e:
    print e
    sys.exit(1)


class PharosConnector(SocketServer.StreamRequestHandler):

    def handle(self):
        if not station.connected():
            try:
                station.start_session(OMEGA, SITEPASS)
            except omega.PharosEDIException as e:
                self.wfile.write("EINTERNAL: Could not reconnect: %s\n" % (str(e)))
        
        data = self.rfile.readline().strip().split()
        if len(data) < 2:
            self.wfile.write("ESYN: Syntax Error\n")
            return
        cmd = data.pop(0)
        # TODO: Dictionary
        if cmd == "getBalance":
            if len(data) > 1:
                self.wfile.write("ESYN: getBalance takes one argument\n")
                return
            try:
                details = station.getUserDetails(data.pop(), False)
                self.wfile.write("OK: %s\n" % (int(details.balance) * 10))
            except omega.PharosEDIException as e:
                self.wfile.write("EINTERNAL: %s\n" % (str(e)))
        elif cmd == "getPrintJobs":
            if len(data) > 1:
                self.wfile.write("ESYN: getUserDetails takes one argument\n")
                return
            rval = ''
            try:
                joblist = station.getPrintJobsForUser(data.pop())
                for j in joblist:
                    rval += "%s\t%s\n" % (j.jobname, j.when_submitted)
            except omega.PharosEDIException as e:
                self.wfile.write("EINTERNAL: %s\n" % (str(e)))
                return
            self.wfile.write("OK: %s\n" % (rval))
        else:
            self.wfile.write("ESYN: Unknown command %s" % (cmd))
        

if __name__ == "__main__":
    try:
        if os.path.exists(SOCKNAME):
            os.remove(SOCKNAME)
    except OSError as e:
        print >>sys.stderr, "Couldn't remove socket (%s): %s" % (SOCKNAME, str(e))
        sys.exit(1)
    server = SocketServer.UnixStreamServer(SOCKNAME, PharosConnector)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    try:
        if os.path.exists(SOCKNAME):
            os.remove(SOCKNAME)
    except OSError as e:
        print >>sys.stderr, "Couldn't remove socket (%s): %s" % (SOCKNAME, str(e))
        sys.exit(1)
    sys.exit(0)

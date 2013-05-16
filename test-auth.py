#!/usr/bin/python

import auth_krb5
import getpass
import logging

logging.basicConfig()
auth_krb5.logger.setLevel(logging.DEBUG)
auth = auth_krb5.Authenticator('pharos-release-station')
print auth.authenticate(raw_input('User: '), getpass.getpass())
print auth.error

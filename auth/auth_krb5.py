import PAM
import sys
import os.path
import logging

# This module uses logging.  To enable it, do something like this in the 
# caller:
# import logging
# logging.basicConfig()
# auth_krb5.logger.setLevel(logging.DEBUG)

# Code inspired by geofft's cruftreg

logger = logging.getLogger('auth_krb5')
logger.addHandler(logging.NullHandler())

class Authenticator():

    def __init__(self, pam_service='python-auth_krb5'):
        self.pam = PAM.pam()
        if not os.path.exists("/etc/pam.d/" + pam_service):
            logger.warn("%s might not be a valid pam service!", pam_service)
        self.pam_service = pam_service
        self.debugPrintPassword = False
        self.error = ''

    def _pam_conversation(self, pam, msgs, response):
        # response unused in this implementation
        # Must return an array of tuples
        logger.debug("PAM Message: %s", msgs)
        if len(msgs) == 1 and msgs[0][1] == PAM.PAM_PROMPT_ECHO_OFF:
            return [(self.password,0)]
        else:
            logger.warn("Unexpected PAM response: ", msgs)
            self.error = msgs[0][0]
            return None
        

    def authenticate(self, user, password):
        logger.debug("authenticate(), user=%s, password=%s", 
                     user, 
                     password if self.debugPrintPassword else "[redacted]")
        self.password = password
        self.pam.start(self.pam_service, user, self._pam_conversation)
        try:
            self.pam.authenticate()
            logger.debug("Authentication successful")
        except PAM.error as error:
            logger.debug("Authentication failed: %s", error)
            self.error = error[0]
            return False
        else:
            return True
        

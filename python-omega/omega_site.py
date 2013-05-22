import suds
import logging

logger = logging.getLogger('local_details')
class Details:
    _mapping = {'employee': 'faculty/staff',
                'student': 'student',
                'other': 'affiliate'}

    def __init__(self, sudsObj):
        if not isinstance(sudsObj, suds.sudsobject.Object):
            raise Exception("Must pass suds.sudsobject.Object")

        self.details = sudsObj
    
    def getAffiliation(self):
        if self.details.group in self._mapping:
            return self._mapping[self.details.group]
        else:
            logger.warn("Cannot map %s to known affiliation", self.details.group)
            return "unknown"
 
    def canExceedQuota(self):
        return self.details.group == "student"

    def getPageBalance(self):
        bal = self.details.balance
        if self.details.group == "student":
            bal -= 10000
        return int(bal * 10)

    def isActive(self):
        return self.details.Active == 1

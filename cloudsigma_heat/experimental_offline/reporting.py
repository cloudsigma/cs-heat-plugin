"""Explicit offline worker endpoint; un-attributed quarantine, never authority."""
import json, sqlite3
from heat.engine.worker import WorkerService
from .admission_model import Refused

class ReportingUnavailable(RuntimeError):
    pass

class QuarantineStore:
    def __init__(self, path, *, offline_opt_in):
        if offline_opt_in is not True: raise Refused('offline opt-in required')
        self.path=path
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS quarantine (slot INTEGER PRIMARY KEY CHECK(slot=1), body TEXT NOT NULL)')
    def record(self):
        # No identity from failed grant, RPC args, exception, or journal is trusted.
        value={'version':1,'state':'UNKNOWN','escalate':True,'attribution':'unidentified','authority':False,'recovery':'separately-trusted-custody-required','convergence_complete':False}
        raw=json.dumps(value,sort_keys=True)
        try:
            with sqlite3.connect(self.path) as db:
                db.execute('INSERT OR REPLACE INTO quarantine(slot,body) VALUES(1,?)',(raw,))
            with sqlite3.connect(self.path) as db:
                if db.execute('SELECT body FROM quarantine WHERE slot=1').fetchone()!=(raw,):raise OSError()
        except Exception:
            raise ReportingUnavailable('offline quarantine storage unavailable') from None
        return value

class OfflineReportingWorker(WorkerService):
    def __init__(self,*args,quarantine,offline_opt_in,**kwargs):
        if offline_opt_in is not True or type(quarantine) is not QuarantineStore:
            raise Refused('offline reporting opt-in required')
        super().__init__(*args,**kwargs)
        self.quarantine=quarantine
    def check_resource(self,*args,**kwargs):
        try:
            return super().check_resource(*args,**kwargs)
        except (Refused, OSError, ValueError, TypeError):
            # No stack/resource failure mutation based on unvalidated custody.
            self.quarantine.record()
            return None

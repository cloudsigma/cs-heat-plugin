"""Explicit caller-trusted OFFLINE registration. Not an operational authority loader.
No default registration, credentials, journal-derived grants, or framework patch.
Caller supplies retained original + continuation and independently pinned refs/source.
"""
from dataclasses import dataclass
from types import MappingProxyType
from . import cleanup, continuation, plugin
from .admission_model import Refused

@dataclass(frozen=True)
class Entry:
    original: cleanup.CleanupGrant
    continuation_path: object
    account: str
    source: str
    references: object

class OfflineRegistry:
    def __init__(self, *, offline_opt_in, entries, cloud, clock, lock_root):
        if offline_opt_in is not True: raise Refused('offline opt-in required')
        self.entries = MappingProxyType(dict(entries))
        self.cloud, self.clock, self.lock_root = cloud, clock, lock_root

    def restore(self, resource):
        entry = self.entries.get((resource.stack.id, resource.id))
        if type(entry) is not Entry: raise Refused('offline custody missing')
        cleanup.validate_grant(entry.original)
        grant = continuation.load(entry.original, entry.continuation_path)
        if grant.account != entry.account or grant.source != entry.source:
            raise Refused('offline trusted binding')
        refs = {k: resource.properties.get(k) for k in ('username','password','vnc_password')}
        if refs != dict(entry.references) or resource._reference_account(refs) != entry.account:
            raise Refused('offline reference binding')
        cap = cleanup.CleanupOnly(self.cloud, grant, self.clock, self.lock_root)
        cap.check(True)
        record = cap.record(resource)
        if resource.resource_id and resource.resource_id != record['id']:
            raise Refused('offline physical binding')
        # Attach only after ALL checks, including the durable journal, succeed.
        resource._offline_lifecycle = cap

    def resource_class(self):
        registry = self
        class OfflineCleanupResource(plugin.CloudSigmaCompute):
            def handle_delete(self):
                cap = getattr(self, '_offline_lifecycle', None)
                if type(cap) is not cleanup.CleanupOnly:
                    raise Refused('offline cleanup custody required')
                self._protected_properties()
                cap.check(True)
                record = cap.record(self)
                if record['phase'] == 'delete-uncertain':
                    # Native Heat always invokes the handler before completion.
                    # Resume observation only; NEVER replay an uncertain DELETE.
                    if not cap.reconcile(self):
                        raise Refused('offline cleanup still visible')
                    return record['id']
                return super().handle_delete()

            def _load_data(self, row):
                self.__dict__.pop('_offline_lifecycle', None)
                try:
                    super()._load_data(row)
                    registry.restore(self)
                except BaseException:
                    self.__dict__.pop('_offline_lifecycle', None)
                    raise
        return OfflineCleanupResource

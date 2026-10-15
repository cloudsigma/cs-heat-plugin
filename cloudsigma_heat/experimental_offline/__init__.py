"""Experimental OFFLINE API. Import never registers or enables a Heat plugin."""
def resource_mapping(*, registry):
    """Return explicit caller-local mapping; never mutate Heat global environment."""
    from .registry_adapter import OfflineRegistry
    if type(registry) is not OfflineRegistry:
        raise TypeError("offline registry required")
    return {"CloudSigma::Compute::Instance": registry.resource_class()}

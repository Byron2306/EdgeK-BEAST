"""Live Level 7 runtime wiring. Network writes remain explicit and fail-closed."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from app.kernel.compute.forge_kv_level7_config import ForgeKVLiveConfig
from app.kernel.compute.forge_kv_credentials import CredentialBroker
from app.kernel.compute.forge_kv_progress import ProgressStream
from app.kernel.compute.forge_kv_commons_state import CommonsContributionState
from app.kernel.compute.forge_kv_production_plane import ForgeKVProductionPlane
from app.kernel.compute.forge_kv_hf_official import OfficialHFDatasetRemote

class Level7Plane(ForgeKVProductionPlane):
    def __init__(self,config:ForgeKVLiveConfig,*,credential_broker:CredentialBroker,api_factory):
        self.config=config
        super().__init__(credential_broker=credential_broker,hf_api_factory=api_factory,progress=ProgressStream(),state=CommonsContributionState(),receipt_root=config.receipt_root)
    def publish_hf(self,**kwargs):
        self.config.validate(for_write=True)
        if self.config.require_private_dataset and kwargs.get("private",True) is not True: raise PermissionError("Level 7 requires a private dataset")
        return super().publish_hf(**kwargs)
    def reachability(self):
        state=super().reachability(); state.update({"level":7,"live_config":self.config.public_state(),"official_hf_adapter":True,"cross_node_evidence":True})
        return state

def mount_level7_router(app:Any,plane:Level7Plane,decode_request):
    from app.kernel.compute.forge_kv_api import create_forge_publication_router
    app.include_router(create_forge_publication_router(plane,decode_request)); return app

"""Narrow official huggingface_hub adapter used by the governed publication plane."""
from __future__ import annotations
from typing import Mapping, Any

class OfficialHFDatasetRemote:
    def __init__(self, api: Any, token: str=""):
        self.api=api
    def ensure_dataset(self, dataset_id: str, *, private: bool=True):
        self.api.create_repo(repo_id=dataset_id, repo_type="dataset", private=private, exist_ok=True)
    def has_chunk(self, dataset_id: str, digest: str) -> bool:
        path=f"xet/objects/{digest[7:9]}/{digest[9:]}"
        try:
            self.api.hf_hub_download(repo_id=dataset_id,repo_type="dataset",filename=path)
            return True
        except Exception as exc:
            name=type(exc).__name__
            if name in {"EntryNotFoundError","RemoteEntryNotFoundError","HfHubHTTPError"}: return False
            return False
    def upload_chunk(self,dataset_id: str,digest: str,payload: bytes):
        self.api.upload_file(path_or_fileobj=payload,path_in_repo=f"xet/objects/{digest[7:9]}/{digest[9:]}",repo_id=dataset_id,repo_type="dataset",commit_message=f"Add Forge chunk {digest[:19]}")
    def commit_files(self,dataset_id: str,files: Mapping[str,bytes],*,message: str,parent_commit: str="") -> str:
        from huggingface_hub import CommitOperationAdd
        ops=[CommitOperationAdd(path_in_repo=p,path_or_fileobj=v) for p,v in sorted(files.items())]
        info=self.api.create_commit(repo_id=dataset_id,repo_type="dataset",operations=ops,commit_message=message,parent_commit=parent_commit or None)
        return str(getattr(info,"oid","") or getattr(info,"commit_url",info))
    def create_branch_and_pr(self,dataset_id: str,files: Mapping[str,bytes],*,branch: str,title: str,description: str):
        try: self.api.create_branch(repo_id=dataset_id,repo_type="dataset",branch=branch,exist_ok=True)
        except TypeError: self.api.create_branch(repo_id=dataset_id,repo_type="dataset",branch=branch)
        from huggingface_hub import CommitOperationAdd
        ops=[CommitOperationAdd(path_in_repo=p,path_or_fileobj=v) for p,v in sorted(files.items())]
        info=self.api.create_commit(repo_id=dataset_id,repo_type="dataset",revision=branch,operations=ops,commit_message=title,create_pr=True)
        return {"commit":str(getattr(info,"oid","") or getattr(info,"commit_url",info)),"pull_request":str(getattr(info,"pr_url","") or getattr(info,"commit_url",""))}

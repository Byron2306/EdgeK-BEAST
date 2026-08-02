"""Operational Hugging Face Hub adapter with branch/PR workflow."""
from __future__ import annotations
from typing import Any, Mapping
class HuggingFaceDatasetRemote:
    def __init__(self,api:Any,token:str,repo_type:str='dataset'): self.api=api; self.token=token; self.repo_type=repo_type
    def ensure_dataset(self,dataset_id:str,*,private:bool): return self.api.create_repo(repo_id=dataset_id,repo_type=self.repo_type,private=private,exist_ok=True,token=self.token)
    def has_chunk(self,dataset_id:str,digest:str)->bool:
        path=f"xet/chunks/{digest[7:9]}/{digest[9:]}"
        try: self.api.hf_hub_download(repo_id=dataset_id,repo_type=self.repo_type,filename=path,token=self.token); return True
        except Exception: return False
    def upload_chunk(self,dataset_id:str,digest:str,payload:bytes):
        return self.api.upload_file(path_or_fileobj=payload,path_in_repo=f"xet/chunks/{digest[7:9]}/{digest[9:]}",repo_id=dataset_id,repo_type=self.repo_type,token=self.token,commit_message=f"Add Forge chunk {digest}")
    def commit_files(self,dataset_id:str,files:Mapping[str,bytes],*,message:str,parent_commit:str='')->str:
        operations=[self.api.CommitOperationAdd(path_in_repo=path,path_or_fileobj=data) for path,data in files.items()]
        result=self.api.create_commit(repo_id=dataset_id,repo_type=self.repo_type,operations=operations,commit_message=message,parent_commit=parent_commit or None,token=self.token)
        return str(getattr(result,'oid',result))
    def create_branch_and_pr(self,dataset_id:str,files:Mapping[str,bytes],*,branch:str,title:str,description:str='')->dict:
        self.api.create_branch(repo_id=dataset_id,repo_type=self.repo_type,branch=branch,token=self.token,exist_ok=True)
        operations=[self.api.CommitOperationAdd(path_in_repo=p,path_or_fileobj=b) for p,b in files.items()]
        commit=self.api.create_commit(repo_id=dataset_id,repo_type=self.repo_type,revision=branch,operations=operations,commit_message=title,token=self.token)
        pr=self.api.create_pull_request(repo_id=dataset_id,repo_type=self.repo_type,title=title,description=description,head=branch,token=self.token)
        return {'branch':branch,'commit':str(getattr(commit,'oid',commit)),'pull_request':str(pr)}

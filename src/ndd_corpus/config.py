from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr


class ProjectConfig(BaseModel):
    name: str = "ndd-literature-corpus"
    tool_name: str = "ndd-literature-corpus"


class DiseaseScopeConfig(BaseModel):
    mondo_root: str = "MONDO:0700092"
    include_descendants: bool = True
    rare_only: bool = True
    use_orphanet: bool = True


class ReferenceConfig(BaseModel):
    mondo_url: str = "https://purl.obolibrary.org/obo/mondo.json"
    mondo_rare_url: str = "https://purl.obolibrary.org/obo/mondo/subsets/mondo-rare.json"
    orphanet_url: str = "https://www.orphadata.com/data/json/en_product1.json.tar.gz"


class PubmedConfig(BaseModel):
    start_year: int = 1900
    end_year: int = 2026
    batch_size: int = Field(default=500, gt=0)
    generic_ndd_query: bool = True
    disease_name_queries: bool = True
    gene_queries: bool = False
    partition_limit: int = Field(default=9999, gt=0, le=9999)


class PmcConfig(BaseModel):
    download_xml: bool = True
    download_txt: bool = False
    download_pdf: bool = False
    download_json_metadata: bool = True
    id_converter_batch_size: int = Field(default=200, gt=0, le=200)
    inventory_bucket_url: str = "https://pmc-oa-opendata.s3.amazonaws.com"


class NetworkConfig(BaseModel):
    max_retries: int = Field(default=8, ge=0)
    timeout_seconds: float = Field(default=60.0, gt=0)
    requests_per_second_without_key: float = Field(default=2.5, gt=0, le=3.0)
    requests_per_second_with_key: float = Field(default=8.0, gt=0, le=10.0)


class PathsConfig(BaseModel):
    data: Path = Path("data")
    raw: Path = Path("data/raw")
    interim: Path = Path("data/interim")
    processed: Path = Path("data/processed")
    logs: Path = Path("data/logs")

    def resolved(self, root: Path) -> PathsConfig:
        values = {
            name: value if value.is_absolute() else (root / value).resolve()
            for name, value in self.model_dump().items()
        }
        return PathsConfig(**values)


class DebugConfig(BaseModel):
    enabled: bool = True
    disease_limit: int = Field(default=10, gt=0)
    pubmed_limit: int = Field(default=100, gt=0)
    pmc_limit: int = Field(default=20, gt=0)


class Settings(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    disease_scope: DiseaseScopeConfig = Field(default_factory=DiseaseScopeConfig)
    reference: ReferenceConfig = Field(default_factory=ReferenceConfig)
    pubmed: PubmedConfig = Field(default_factory=PubmedConfig)
    pmc: PmcConfig = Field(default_factory=PmcConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    debug: DebugConfig = Field(default_factory=DebugConfig)
    repository_root: Path
    ncbi_email: str | None = Field(default=None, repr=False)
    ncbi_api_key: SecretStr | None = Field(default=None, repr=False)

    @classmethod
    def load(
        cls,
        path: str | Path = "configs/default.yaml",
        *,
        env: Mapping[str, str] | None = None,
    ) -> Settings:
        config_path = Path(path).expanduser().resolve()
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"configuration root must be a mapping: {config_path}")
        root = (
            config_path.parent.parent
            if config_path.parent.name == "configs"
            else config_path.parent
        )
        source_env: dict[str, str] = {}
        if env is None:
            source_env.update(
                {key: value for key, value in dotenv_values(root / ".env").items() if value}
            )
            source_env.update(os.environ)
        else:
            source_env.update(env)
        raw["repository_root"] = root
        raw["ncbi_email"] = source_env.get("NCBI_EMAIL") or None
        raw["ncbi_api_key"] = source_env.get("NCBI_API_KEY") or None
        settings = cls.model_validate(raw)
        return settings.model_copy(update={"paths": settings.paths.resolved(root)})

    def require_ncbi_credentials(self) -> None:
        if not self.ncbi_email:
            raise ValueError("NCBI_EMAIL is required for live NCBI operations")

    def safe_metadata(self) -> dict[str, Any]:
        return {
            "project": self.project.name,
            "repository_root": str(self.repository_root),
            "ncbi_email_configured": bool(self.ncbi_email),
            "ncbi_api_key_configured": self.ncbi_api_key is not None,
            "debug": self.debug.enabled,
        }

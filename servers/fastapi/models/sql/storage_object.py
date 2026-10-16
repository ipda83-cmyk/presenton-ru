"""Where each file of APP_DATA_DIRECTORY lives in the external file storage.

The container disk is not persistent on some hosts (RelaxNet), so files are
copied to the platform Storage API and restored after a redeploy. The storage
picks the final object name itself (it prefixes a timestamp), hence this map.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime
from sqlmodel import Field, SQLModel

from utils.datetime_utils import get_current_utc_datetime


class StorageObject(SQLModel, table=True):
    __tablename__ = "storage_objects"

    # Path relative to APP_DATA_DIRECTORY, "/" separated.
    path: str = Field(primary_key=True, max_length=1024)
    remote_path: str = Field(max_length=1024)
    url: str = Field(max_length=2048)
    fallback_url: str | None = Field(default=None, max_length=2048)
    sha256: str = Field(max_length=64)
    size: int = Field(sa_column=Column(BigInteger, nullable=False))
    updated_at: datetime = Field(
        default_factory=get_current_utc_datetime,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

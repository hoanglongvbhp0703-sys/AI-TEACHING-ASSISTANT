from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProcessingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    embedding_model: str | None = Field(default=None, min_length=1, max_length=200)
    parser_revision: str | None = Field(default=None, min_length=1, max_length=100)
    chunk_size: int | None = Field(default=None, ge=64, le=32768)
    chunk_overlap: int | None = Field(default=None, ge=0, le=32767)

    @model_validator(mode="after")
    def overlap(self):
        if self.chunk_overlap is not None and (
            self.chunk_size is None or self.chunk_overlap >= self.chunk_size
        ):
            raise ValueError("chunk_overlap requires chunk_size and must be smaller")
        return self


class ReindexInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extraction_config: ProcessingConfig | None = None
    change_note: str = Field(default="Reindex", max_length=2000)

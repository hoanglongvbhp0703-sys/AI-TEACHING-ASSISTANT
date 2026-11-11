"""Lazy local models, with Vietnamese segmentation required by BKAI's model card."""

import os
from pathlib import Path


class LocalModels:
    def __init__(self, settings):
        self.settings = settings
        self.encoders = {}
        self.reranker = None

    def encoder(self, name):
        if name not in self.encoders:
            self._environment()
            from sentence_transformers import SentenceTransformer

            self.encoders[name] = SentenceTransformer(
                name,
                device=self.settings.rag_device,
                cache_folder=str(self.settings.rag_model_cache / "hub"),
                trust_remote_code=False,
            )
        return self.encoders[name]

    def _environment(self):
        os.environ.setdefault("HF_HOME", str(Path(self.settings.rag_model_cache).resolve()))
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        import torch

        torch.set_num_threads(self.settings.rag_cpu_threads)

    @staticmethod
    def segmented(text):
        from pyvi import ViTokenizer

        return ViTokenizer.tokenize(text)

    def fits(self, text, name):
        model = self.encoder(name)
        return (
            len(model.tokenizer.encode(self.segmented(text), verbose=False)) <= model.max_seq_length
        )

    def embed(self, texts, name):
        return (
            self.encoder(name)
            .encode(
                [self.segmented(text) for text in texts],
                batch_size=16,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            .tolist()
        )

    def rerank(self, question, texts):
        if self.reranker is None:
            self._environment()
            from sentence_transformers import CrossEncoder

            self.reranker = CrossEncoder(
                self.settings.rag_reranker_model,
                device=self.settings.rag_device,
                cache_folder=str(self.settings.rag_model_cache / "hub"),
                trust_remote_code=False,
            )
        import torch

        return self.reranker.predict(
            [(question, t) for t in texts],
            batch_size=10,
            activation_fn=torch.nn.Sigmoid(),
            show_progress_bar=False,
        ).tolist()

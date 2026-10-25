"""DeepEval custom judge: exact configured OpenAI models and structured output."""
import os
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
from deepeval.models import DeepEvalBaseLLM
from rag_engine.llm_client import get_openai_client, get_async_openai_client, response_options, response_text


class OpenAIJudge(DeepEvalBaseLLM):
    def __init__(self, task="mini"):
        self.task = task
        super().__init__(model=response_options(task)["model"])

    def load_model(self):
        return get_openai_client()

    def get_model_name(self):
        return response_options(self.task)["model"]

    def generate(self, prompt, schema=None):
        options = {**response_options(self.task), "input": prompt}
        client = self.load_model()
        if schema is None:
            return response_text(client.responses.create(**options))
        response = client.responses.parse(**options, text_format=schema)
        response_text(response)
        if response.output_parsed is None:
            raise RuntimeError("Evaluation judge did not produce the requested JSON schema")
        return response.output_parsed

    async def a_generate(self, prompt, schema=None):
        options = {**response_options(self.task), "input": prompt}
        client = get_async_openai_client()
        if schema is None:
            return response_text(await client.responses.create(**options))
        response = await client.responses.parse(**options, text_format=schema)
        response_text(response)
        if response.output_parsed is None:
            raise RuntimeError("Evaluation judge did not produce the requested JSON schema")
        return response.output_parsed

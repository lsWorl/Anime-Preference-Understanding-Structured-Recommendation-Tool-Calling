"""Download exactly the model/tokenizer snapshot used by all experiments."""
from huggingface_hub import snapshot_download
if __name__=='__main__':
    print(snapshot_download('Qwen/Qwen3-4B',revision='1cfa9a7208912126459214e8b04321603b3df60c'))

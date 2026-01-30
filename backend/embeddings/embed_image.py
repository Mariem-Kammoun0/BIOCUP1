import numpy as np
from PIL import Image
import torch
import open_clip

_device = "cuda" if torch.cuda.is_available() else "cpu"

# IMPORTANT: use a non-HF pretrained tag (open_clip weights)
_model, _, _preprocess = open_clip.create_model_and_transforms(
    "ViT-B-32", pretrained="openai"   # <- avoids HF in most setups
)
_model = _model.to(_device).eval()

@torch.no_grad()
def embed_image(img: Image.Image) -> np.ndarray:
    x = _preprocess(img).unsqueeze(0).to(_device)
    vec = _model.encode_image(x)
    vec = vec / vec.norm(dim=-1, keepdim=True)
    return vec.squeeze(0).detach().cpu().numpy().astype(np.float32)

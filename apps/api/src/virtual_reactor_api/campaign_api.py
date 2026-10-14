"""Campaign concept generation boundary. OpenAI is intentionally server-side."""
import base64, json, os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/campaigns", tags=["campaigns"])

class CampaignRequest(BaseModel):
    brief: str = Field(min_length=3)
    audience: str = Field(min_length=2)
    product: str = Field(min_length=2)
    tone: str = Field(min_length=2)
    channels: list[str] = Field(min_length=1)

@router.post("/generate")
def generate_campaign(request: CampaignRequest):
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, "OPENAI_API_KEY 未配置，请在服务端环境变量中设置。")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        prompt = f"""You are a senior brand strategist. Create a practical campaign direction from this brief.
Return ONLY valid JSON with keys: concept (object with name, promise, rationale), variants (array of exactly 3 objects with headline, body, channel), checklist (array of strings), image_prompts (array of exactly 2 strings).
Brief: {request.brief}\nAudience: {request.audience}\nProduct: {request.product}\nTone: {request.tone}\nChannels: {', '.join(request.channels)}"""
        response = client.responses.create(model=os.getenv("CAMPAIGN_TEXT_MODEL", "gpt-5.4"), input=prompt)
        data = json.loads(response.output_text)
        images = []
        for image_prompt in data.get("image_prompts", [])[:2]:
            result = client.images.generate(model=os.getenv("CAMPAIGN_IMAGE_MODEL", "gpt-image-1"), prompt=image_prompt, size="1024x1024", quality="low", n=1)
            b64 = result.data[0].b64_json if result.data else None
            if b64: images.append(f"data:image/png;base64,{b64}")
        data["images"] = images
        return data
    except json.JSONDecodeError as error:
        raise HTTPException(502, "模型返回的 campaign JSON 无法解析。") from error
    except Exception as error:
        raise HTTPException(502, f"Campaign 生成失败：{error}") from error

"""
RunPod Ollama 연결 테스트 스크립트
EEVE 모델이 정상적으로 응답하는지 확인합니다.
"""

import requests
from config import OLLAMA_BASE_URL, MODEL_NAME, TEMPERATURE, NUM_CTX

def test_ollama_connection():
    """Ollama 연결 및 EEVE 모델 응답 테스트"""
    print("=" * 60)
    print("RunPod Ollama Connection Test")
    print("=" * 60)
    print(f"URL: {OLLAMA_BASE_URL}")
    print(f"Model: {MODEL_NAME}")
    print("-" * 60)

    # 1. Chat endpoint 테스트
    chat_url = f"{OLLAMA_BASE_URL.rstrip('/')}/chat"
    print(f"\n[TEST 1] Chat endpoint: {chat_url}")

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "안녕하세요. 1+1은?"}
        ],
        "options": {
            "temperature": TEMPERATURE,
            "num_ctx": NUM_CTX
        },
        "stream": False  # 스트리밍 비활성화
    }

    try:
        print("Sending request...")
        response = requests.post(chat_url, json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("\n[SUCCESS] Response received:")
            print(f"Full Response: {data}")

            if "message" in data:
                content = data["message"].get("content", "")
                print(f"\nExtracted Content: {content[:200]}")
                print("\n✓ EEVE model is working correctly!")
                return True
            else:
                print("\n✗ Unexpected response format (no 'message' key)")
                return False
        else:
            print(f"\n✗ HTTP Error: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False

    except requests.exceptions.Timeout:
        print("\n✗ Connection timeout - RunPod pod may be sleeping or stopped")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"\n✗ Connection error: {e}")
        print("Check if RunPod URL is correct and pod is running")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return False

    print("=" * 60)


def test_models_list():
    """사용 가능한 모델 목록 확인"""
    print("\n" + "=" * 60)
    print("[TEST 2] Available models list")
    print("=" * 60)

    # Ollama tags endpoint
    tags_url = f"{OLLAMA_BASE_URL.rstrip('/')}/tags"
    print(f"Checking: {tags_url}")

    try:
        response = requests.get(tags_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            print(f"\nFound {len(models)} models:")
            for model in models:
                name = model.get("name", "unknown")
                size = model.get("size", 0) / (1024**3)  # GB
                print(f"  - {name} ({size:.2f} GB)")

            # Check if EEVE exists
            model_names = [m.get("name", "") for m in models]
            if MODEL_NAME in model_names or any(MODEL_NAME in m for m in model_names):
                print(f"\n✓ Model '{MODEL_NAME}' found!")
            else:
                print(f"\n✗ Model '{MODEL_NAME}' NOT found in available models")
                print(f"   Available: {model_names}")
        else:
            print(f"✗ Could not fetch models (status: {response.status_code})")
    except Exception as e:
        print(f"✗ Error fetching models: {e}")


if __name__ == "__main__":
    success = test_ollama_connection()
    test_models_list()

    print("\n" + "=" * 60)
    if success:
        print("RESULT: ✓ Connection successful - EEVE is ready to use")
    else:
        print("RESULT: ✗ Connection failed - Check RunPod pod status")
    print("=" * 60)

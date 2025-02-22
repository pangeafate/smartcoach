# openai_integration.py
import os
import json
import requests

def query_openai(prompt: str) -> str:
    try:
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1000,
            "temperature": 0.7
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"OpenAI API error: {response.status_code} - {response.text}")
            return "Sorry, I couldn't process that prompt."
    except Exception as e:
        print("Error calling OpenAI API:", e)
        return "Sorry, I couldn't process that prompt."

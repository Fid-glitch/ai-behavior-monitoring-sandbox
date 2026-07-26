from providers.groq_provider import GroqProvider

provider = GroqProvider()
response = provider.generate("Say hello and tell me you're working correctly.")
print(response)
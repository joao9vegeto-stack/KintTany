# Qwen Coder iOS

Aplicativo iOS nativo em SwiftUI para conversar com Qwen3-Coder através de um endpoint OpenAI-compatible.

## Modelo padrão
- Qwen/Qwen3-Coder-30B-A3B-Instruct

## Endpoint padrão
- https://router.huggingface.co/v1

Você também pode apontar para qualquer servidor vLLM/SGLang/OpenAI-compatible, inclusive um servidor próprio.

## Build
O workflow `.github/workflows/ios.yml` gera um IPA unsigned próprio para sideload/reassinatura.

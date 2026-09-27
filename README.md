# Qwen Coder iOS

Aplicativo iOS nativo em SwiftUI para conversar com o Qwen3-Coder por um endpoint OpenAI-compatible.

## Padrão
- Endpoint: `https://router.huggingface.co/v1`
- Modelo: `Qwen/Qwen3-Coder-30B-A3B-Instruct:preferred`

O roteador da Hugging Face exige um token de usuário. O app abre a configuração automaticamente quando o token ainda não foi informado e não envia requisições sem autenticação.

Também é possível usar um endpoint próprio vLLM/SGLang/OpenAI-compatible, com ou sem autenticação.

## Build
O workflow `.github/workflows/ios.yml` gera um IPA unsigned para sideload/reassinatura.

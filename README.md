# Qwen3-Coder — branch isolada

Esta branch foi criada do zero em termos de conteúdo para executar o Quick Start oficial do Qwen3-Coder sem alterar nenhuma outra branch do repositório.

## O que há aqui

- `qwen3_coder_quickstart.py`: exemplo executável baseado no Quick Start oficial.
- `requirements.txt`: dependências declaradas pelo repositório oficial Qwen3-Coder.
- `requirements-quickstart.txt`: dependências mínimas para o exemplo com Transformers.
- `setup.sh`: cria um ambiente virtual e instala as dependências.
- `.github/workflows/qwen3-coder.yml`: valida a instalação mínima e a sintaxe sem baixar os pesos do modelo.

## Instalação rápida

```bash
chmod +x setup.sh
./setup.sh
source .venv/bin/activate
python qwen3_coder_quickstart.py "Escreva uma função Swift para ordenar um array."
```

Por padrão o script usa `Qwen/Qwen3-Coder-Next`.

Para instalar também as dependências completas declaradas pelo repositório oficial, incluindo `vllm`:

```bash
./setup.sh --full
```

## Observação importante

O Quick Start oficial é Python/PyTorch/Transformers, não um projeto Swift/iOS. O modelo é grande e o uso local exige hardware compatível. O workflow desta branch verifica a instalação mínima e os imports, mas não baixa nem executa os pesos completos do modelo em um runner comum do GitHub Actions.
